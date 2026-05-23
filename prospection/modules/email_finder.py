"""
Module Email Finder — Extraction d'emails depuis les sites web des parapharmacies.
Zéro plantage : toutes les erreurs réseau sont interceptées et loggées.
"""

import sys
import os
import re
import time
from typing import List, Optional

import requests
import urllib3

# Désactiver les avertissements SSL (sites avec certificats invalides)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import creer_logger, DELAI_EMAIL, TIMEOUT_EMAIL
from modules.modeles import Parapharmacie

logger = creer_logger("email_finder")

# Regex stricte pour capturer les emails valides
REGEX_EMAIL = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}\b')

# Patterns à ignorer (faux positifs courants dans les pages web)
EMAILS_A_IGNORER = [
    "noreply", "no-reply", "donotreply", "example",
    "test", "admin", "webmaster", "wordpress",
    "woocommerce", "sentry", "support",
    ".png", ".jpg", ".gif", ".js", ".css", ".svg",
]

# Pages à visiter sur le site, dans l'ordre
CHEMINS_CONTACT = ["", "/contact", "/nous-contacter", "/a-propos"]

# Headers navigateur pour éviter les blocages
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def est_email_valide(email: str) -> bool:
    """Vérifie qu'un email n'est pas un faux positif connu."""
    email_lower = email.lower()
    return not any(pattern in email_lower for pattern in EMAILS_A_IGNORER)


def choisir_meilleur_email(emails: List[str]) -> str:
    """Sélectionne le meilleur email : contact > info > premier valide."""
    if not emails:
        return ""

    for email in emails:
        if email.lower().startswith("contact@"):
            return email

    for email in emails:
        if email.lower().startswith("info@"):
            return email

    return emails[0]


def extraire_emails_depuis_html(html: str) -> List[str]:
    """Extrait et filtre les emails valides depuis un contenu HTML."""
    emails_bruts = REGEX_EMAIL.findall(html)
    vus = set()
    emails_valides = []

    for email in emails_bruts:
        email_lower = email.lower()
        if est_email_valide(email) and email_lower not in vus:
            vus.add(email_lower)
            emails_valides.append(email)

    return emails_valides


def visiter_page(session: requests.Session, url: str) -> Optional[str]:
    """Visite une URL et retourne le HTML, ou None en cas d'erreur."""
    try:
        reponse = session.get(
            url,
            timeout=TIMEOUT_EMAIL,
            verify=False,
            allow_redirects=True,
        )
        content_type = reponse.headers.get("content-type", "")
        if "text/html" in content_type or "text/plain" in content_type:
            return reponse.text
        return None

    except requests.Timeout:
        logger.debug(f"Timeout : {url}")
        return None
    except requests.ConnectionError:
        logger.debug(f"Connexion impossible : {url}")
        return None
    except requests.TooManyRedirects:
        logger.debug(f"Trop de redirections : {url}")
        return None
    except Exception as e:
        logger.debug(f"Erreur pour {url} : {e}")
        return None


def normaliser_url(site_web: str) -> str:
    """S'assure que l'URL commence par http(s)://."""
    site_web = site_web.strip().rstrip("/")
    if not site_web.startswith("http"):
        site_web = "https://" + site_web
    return site_web


def trouver_email(site_web: str) -> str:
    """
    Cherche un email sur un site web en visitant les pages de contact.
    S'arrête dès qu'un email valide est trouvé.
    """
    if not site_web:
        return ""

    url_base = normaliser_url(site_web)

    session = requests.Session()
    session.max_redirects = 3
    session.headers.update(HEADERS)

    for chemin in CHEMINS_CONTACT:
        url = url_base + chemin
        html = visiter_page(session, url)

        if html:
            emails = extraire_emails_depuis_html(html)
            if emails:
                meilleur = choisir_meilleur_email(emails)
                logger.info(f"Email trouvé sur {url} : {meilleur}")
                return meilleur

        time.sleep(DELAI_EMAIL)

    return ""


def enrichir(parapharmacies: List[Parapharmacie], zone: str = "") -> List[Parapharmacie]:
    """
    Enrichit les Parapharmacies avec des emails trouvés sur leurs sites web.
    Les téléphones sont déjà normalisés depuis la Phase 1 (OSM).
    """
    from config import sauvegarder_progression

    total = len(parapharmacies)
    enrichis = 0

    for i, p in enumerate(parapharmacies):
        print(f"  [Email {i+1}/{total}] {p.nom[:45]:<45}", end="\r")

        # Email déjà renseigné depuis OSM → pas besoin de chercher
        if p.email:
            logger.debug(f"Email déjà présent pour '{p.nom}' : {p.email}")
            continue

        # Impossible de chercher sans site web
        if not p.site_web:
            continue

        email_trouve = trouver_email(p.site_web)

        if email_trouve:
            p.email = email_trouve
            parapharmacies[i] = p
            enrichis += 1
            logger.info(f"Email finder : '{p.nom}' → {email_trouve}")

        # Sauvegarde progressive toutes les 10 entrées
        if (i + 1) % 10 == 0 and zone:
            sauvegarder_progression(parapharmacies, zone, 4)

    print()  # Saut de ligne après la progression

    logger.info(f"Email finder terminé : {enrichis}/{total} emails trouvés")
    if zone:
        sauvegarder_progression(parapharmacies, zone, 4)
    return parapharmacies


if __name__ == "__main__":
    import glob
    import json
    from config import BASE_DIR

    print("=" * 55)
    print("  TEST MODULE EMAIL FINDER — Lyon")
    print("=" * 55)

    # Charger les données depuis le cache
    for pattern in [
        os.path.join(BASE_DIR, "cache", "progression_lyon_phase3.json"),
        os.path.join(BASE_DIR, "cache", "progression_lyon_phase2.json"),
    ]:
        fichiers = glob.glob(pattern)
        if fichiers:
            break
    else:
        fichiers = glob.glob(os.path.join(BASE_DIR, "cache", "osm_lyon_*.json"))

    if not fichiers:
        print("  [INFO] Cache absent, lancement OSM...")
        from modules import osm
        donnees = osm.rechercher("Lyon")
    else:
        fichier = sorted(fichiers)[-1]
        print(f"  [INFO] Chargement : {os.path.basename(fichier)}")
        with open(fichier, 'r', encoding='utf-8') as f:
            donnees = [Parapharmacie(**d) for d in json.load(f)]

    # Filtrer les entrées avec site web (les seules où on peut trouver un email)
    avec_site = [p for p in donnees if p.site_web]
    sans_email = [p for p in avec_site if not p.email]
    print(f"  [INFO] {len(avec_site)} entrées avec site web, {len(sans_email)} sans email\n")

    donnees_test = avec_site[:5]
    donnees_enrichies = enrichir(donnees_test)

    print(f"\n{'=' * 55}")
    print("  RÉSULTATS EMAIL FINDER :")
    avec_email = sum(1 for p in donnees_enrichies if p.email)
    print(f"  Emails trouvés : {avec_email}/{len(donnees_enrichies)}\n")

    for p in donnees_enrichies:
        email = p.email if p.email else "—"
        print(f"  {p.nom[:42]:<42} → {email}")

    print(f"{'=' * 55}")
