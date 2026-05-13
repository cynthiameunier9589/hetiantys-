"""
Module d'enrichissement automatique des fiches pharmacies.
Sources : Pappers API → recherche email Google → Pages Jaunes fiche détaillée.
"""

import logging
import time
import random
import re
from typing import Optional, Callable, Dict, Any, List

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from database import mettre_a_jour_pharmacie, lister_pharmacies

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36",
]

EMAILS_BLACKLIST = {
    "noreply", "no-reply", "contact@pagesjaunes", "donotreply",
    "mailer-daemon", "postmaster", "abuse", "spam",
}

QUALITES_DECIDANT = {
    "pharmacien titulaire", "titulaire", "gérant", "president", "président",
    "directeur général", "associé gérant",
}


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }


def _get(url: str, timeout: int = 15) -> Optional[requests.Response]:
    """Requête GET avec gestion des erreurs réseau et SSL désactivé pour Mac/LibreSSL."""
    for tentative in range(3):
        try:
            resp = requests.get(url, headers=_headers(), timeout=timeout, verify=False)
            if resp.status_code == 429:
                time.sleep(10)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"Erreur réseau {url} (tentative {tentative+1}) : {e}")
            if tentative < 2:
                time.sleep(2 * (tentative + 1))
    return None


def _extraire_emails(texte: str) -> List[str]:
    """Extrait les emails d'un texte et filtre les emails génériques."""
    pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    emails = re.findall(pattern, texte)
    filtres = []
    for email in emails:
        email_lower = email.lower()
        if not any(bl in email_lower for bl in EMAILS_BLACKLIST):
            filtres.append(email)
    return list(dict.fromkeys(filtres))  # Dédoublonnage ordre préservé


# ─── PAPPERS API ───────────────────────────────────────────────────────────────

def enrichir_pappers(nom: str, ville: str, api_token: str) -> Dict[str, Any]:
    """Recherche dirigeant + CA exact via l'API Pappers."""
    resultat = {}
    if not api_token:
        return resultat

    q = f"{nom} {ville}".replace(" ", "+")
    url = f"https://api.pappers.fr/v2/recherche?q={q}&api_token={api_token}"

    resp = _get(url)
    if not resp:
        return resultat

    try:
        data = resp.json()
        resultats = data.get("resultats", [])
        if not resultats:
            return resultat

        entreprise = resultats[0]

        # Dirigeant principal
        dirigeants = entreprise.get("dirigeants", [])
        for dirigeant in dirigeants:
            qualite = (dirigeant.get("qualite") or "").lower()
            if any(q in qualite for q in QUALITES_DECIDANT):
                resultat["nom_decidant"] = dirigeant.get("nom", "")
                resultat["prenom_decidant"] = dirigeant.get("prenom", "")
                break

        if "nom_decidant" not in resultat and dirigeants:
            resultat["nom_decidant"] = dirigeants[0].get("nom", "")
            resultat["prenom_decidant"] = dirigeants[0].get("prenom", "")

    except Exception as e:
        logger.error(f"Erreur parsing Pappers pour {nom} {ville} : {e}")

    return resultat


# ─── RECHERCHE EMAIL VIA GOOGLE ────────────────────────────────────────────────

def enrichir_email_google(nom: str, ville: str, code_postal: str) -> Optional[str]:
    """Tente de trouver l'email de la pharmacie via une recherche Google."""
    requete = f"{nom} {ville} {code_postal} email contact pharmacie".replace(" ", "+")
    url = f"https://www.google.com/search?q={requete}&hl=fr"

    resp = _get(url)
    if not resp:
        return None

    emails = _extraire_emails(resp.text)
    # Filtrer les emails de domaines hors pharmacie
    for email in emails:
        domaine = email.split("@")[-1].lower()
        if domaine not in ("google.com", "pagesjaunes.fr", "w3.org", "schema.org"):
            return email
    return None


# ─── PAGES JAUNES FICHE DÉTAILLÉE ─────────────────────────────────────────────

def enrichir_pages_jaunes_detail(nom: str, ville: str) -> Optional[str]:
    """Cherche l'email sur la fiche Pages Jaunes détaillée."""
    terme = f"{nom} {ville}".replace(" ", "+")
    url_recherche = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui={terme}&ou={ville.replace(' ', '+')}"

    resp = _get(url_recherche)
    if not resp:
        return None

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        email_links = soup.select("a[href^='mailto:']")
        for link in email_links:
            email = link.get("href", "").replace("mailto:", "").strip()
            if email and not any(bl in email.lower() for bl in EMAILS_BLACKLIST):
                return email
    except Exception as e:
        logger.error(f"Erreur PJ détail {nom} {ville} : {e}")

    return None


# ─── ENRICHISSEMENT D'UNE PHARMACIE ───────────────────────────────────────────

def enrichir_pharmacie(
    db_path: str,
    pharmacie: Dict[str, Any],
    api_token: str = "",
    callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Enrichit une pharmacie (dirigeant + email) depuis toutes les sources.
    Retourne True si au moins une information a été trouvée.
    """
    nom = pharmacie["nom"] or ""
    ville = pharmacie["ville"] or ""
    code_postal = pharmacie["code_postal"] or ""
    pharmacie_id = pharmacie["id"]

    mise_a_jour = {}

    def log(msg: str):
        logger.info(msg)
        if callback:
            callback(msg)

    log(f"Enrichissement : {nom} ({ville})")

    # Étape 1 — Pappers
    if api_token and not pharmacie.get("nom_decidant"):
        log(f"  → Pappers API...")
        infos_pappers = enrichir_pappers(nom, ville, api_token)
        if infos_pappers.get("nom_decidant"):
            mise_a_jour.update(infos_pappers)
            log(f"  ✓ Dirigeant trouvé : {infos_pappers.get('prenom_decidant', '')} {infos_pappers['nom_decidant']}")
        time.sleep(random.uniform(0.8, 1.5))

    # Étape 2 — Email Google
    if not pharmacie.get("email"):
        log(f"  → Recherche email Google...")
        email = enrichir_email_google(nom, ville, code_postal)
        if email:
            mise_a_jour["email"] = email
            log(f"  ✓ Email trouvé : {email}")
        time.sleep(random.uniform(2.5, 4.0))

    # Étape 3 — Pages Jaunes fiche détaillée
    if not mise_a_jour.get("email"):
        log(f"  → Pages Jaunes fiche détaillée...")
        email_pj = enrichir_pages_jaunes_detail(nom, ville)
        if email_pj:
            mise_a_jour["email"] = email_pj
            log(f"  ✓ Email PJ trouvé : {email_pj}")
        time.sleep(random.uniform(1.5, 2.5))

    # Enregistrement si au moins une info trouvée
    if mise_a_jour:
        mise_a_jour["enrichi"] = 1
        mettre_a_jour_pharmacie(db_path, pharmacie_id, mise_a_jour)
        return True
    else:
        # Marquer comme "tenté" sans succès pour ne pas reboucler
        mettre_a_jour_pharmacie(db_path, pharmacie_id, {"enrichi": 1})
        log(f"  ✗ Aucune information trouvée")
        return False


# ─── ENRICHISSEMENT PAR LOT ────────────────────────────────────────────────────

def enrichir_lot(
    db_path: str,
    api_token: str = "",
    callback_progress: Optional[Callable[[int, int, str], None]] = None,
    stop_flag: Optional[list] = None,
) -> Dict[str, int]:
    """
    Enrichit toutes les pharmacies non encore enrichies.
    callback_progress(actuel, total, message) pour la barre de progression.
    stop_flag est une liste d'un élément ; si stop_flag[0] == True, on arrête.
    """
    pharmacies = lister_pharmacies(db_path, non_enrichies_only=True)
    total = len(pharmacies)
    compteurs = {"enrichies": 0, "sans_resultat": 0, "erreurs": 0}

    for i, pharmacie in enumerate(pharmacies):
        if stop_flag and stop_flag[0]:
            break

        try:
            succes = enrichir_pharmacie(
                db_path,
                dict(pharmacie),
                api_token=api_token,
                callback=lambda msg: callback_progress and callback_progress(i + 1, total, msg),
            )
            if succes:
                compteurs["enrichies"] += 1
            else:
                compteurs["sans_resultat"] += 1
        except Exception as e:
            compteurs["erreurs"] += 1
            logger.error(f"Erreur enrichissement {pharmacie['nom']} : {e}")

        if callback_progress:
            callback_progress(i + 1, total, f"Traitement {i + 1}/{total} — {pharmacie['nom']}")

        # Délai poli entre les requêtes
        time.sleep(random.uniform(2, 4))

    return compteurs
