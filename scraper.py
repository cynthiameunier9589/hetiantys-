"""
Module de scraping des pharmacies par département.
Sources : API annuaire santé (FHIR) + Pages Jaunes.
"""

import logging
import time
import random
from typing import Callable, Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup

from database import inserer_pharmacie, pharmacie_existe

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

REGIONS_DEPARTEMENTS = {
    "Auvergne-Rhône-Alpes": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "Bourgogne-Franche-Comté": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "Bretagne": ["22", "29", "35", "56"],
    "Centre-Val de Loire": ["18", "28", "36", "37", "41", "45"],
    "Corse": ["2A", "2B"],
    "Grand Est": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "Hauts-de-France": ["02", "59", "60", "62", "80"],
    "Île-de-France": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "Normandie": ["14", "27", "50", "61", "76"],
    "Nouvelle-Aquitaine": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "Occitanie": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "Pays de la Loire": ["44", "49", "53", "72", "85"],
    "Provence-Alpes-Côte d'Azur": ["04", "05", "06", "13", "83", "84"],
    "DOM-TOM": ["971", "972", "973", "974", "976"],
}


def _headers_json() -> Dict[str, str]:
    """Headers pour l'API FHIR annuaire santé."""
    return {
        "Accept": "application/fhir+json, application/json",
        "User-Agent": random.choice(USER_AGENTS),
    }


def _headers_web() -> Dict[str, str]:
    """Headers pour le scraping web."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }


def _get(url: str, headers: dict, timeout: int = 20) -> Optional[requests.Response]:
    """Requête GET avec gestion d'erreurs et retry sur 429."""
    for tentative in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                time.sleep(5 * (tentative + 1))
                continue
            if resp.status_code == 200:
                return resp
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Erreur réseau {url} : {e}")
            if tentative < 2:
                time.sleep(2)
    return None


# ─── SOURCE 1 : API Annuaire Santé (FHIR) ─────────────────────────────────────

def scraper_api_sante_departement(departement: str, callback=None) -> List[Dict[str, Any]]:
    """
    Interroge l'API FHIR annuaire santé avec le préfixe département.
    Utilise address-postalcode avec préfixe pour couvrir tout le département.
    """
    pharmacies = []
    prefixe = departement.zfill(2) if len(departement) <= 2 else departement

    # Recherche par préfixe de code postal (ex: 42 couvre tous les 42xxx)
    url = (
        f"https://api.annuaire.sante.fr/fhir/v1/Organization"
        f"?type=PHAR"
        f"&address-postalcode={prefixe}*"
        f"&_count=200"
        f"&active=true"
    )

    if callback:
        callback(f"  → API annuaire santé : département {departement}...")

    resp = _get(url, _headers_json())
    if not resp:
        if callback:
            callback(f"  ✗ API santé non disponible pour le département {departement}")
        return pharmacies

    try:
        data = resp.json()
        entrees = data.get("entry", [])
        total = data.get("total", 0)

        if callback:
            callback(f"  ✓ API santé : {total} établissements trouvés")

        for entree in entrees:
            resource = entree.get("resource", {})
            nom = resource.get("name", "").strip()
            if not nom:
                continue

            # Adresse
            adresses = resource.get("address", [])
            adresse_data = adresses[0] if adresses else {}
            lignes = adresse_data.get("line", [])
            adresse = " ".join(lignes).strip()
            ville = adresse_data.get("city", "").title()
            cp = adresse_data.get("postalCode", "")

            # Téléphone
            telecoms = resource.get("telecom", [])
            telephone = next(
                (t.get("value", "") for t in telecoms if t.get("system") == "phone"), ""
            )

            if nom and cp:
                pharmacies.append({
                    "nom": nom.title(),
                    "adresse": adresse or None,
                    "ville": ville or None,
                    "code_postal": cp,
                    "departement": departement,
                    "telephone": telephone or None,
                    "source": "scraping_data_gouv",
                })

        # Pagination : récupérer les pages suivantes
        liens = data.get("link", [])
        url_suivante = next(
            (l.get("url") for l in liens if l.get("relation") == "next"), None
        )

        page = 1
        while url_suivante and page < 10:
            time.sleep(0.5)
            resp_suiv = _get(url_suivante, _headers_json())
            if not resp_suiv:
                break
            data_suiv = resp_suiv.json()
            for entree in data_suiv.get("entry", []):
                resource = entree.get("resource", {})
                nom = resource.get("name", "").strip()
                if not nom:
                    continue
                adresses = resource.get("address", [])
                adresse_data = adresses[0] if adresses else {}
                lignes = adresse_data.get("line", [])
                adresse = " ".join(lignes).strip()
                ville = adresse_data.get("city", "").title()
                cp = adresse_data.get("postalCode", "")
                telecoms = resource.get("telecom", [])
                telephone = next(
                    (t.get("value", "") for t in telecoms if t.get("system") == "phone"), ""
                )
                if nom and cp:
                    pharmacies.append({
                        "nom": nom.title(),
                        "adresse": adresse or None,
                        "ville": ville or None,
                        "code_postal": cp,
                        "departement": departement,
                        "telephone": telephone or None,
                        "source": "scraping_data_gouv",
                    })
            liens = data_suiv.get("link", [])
            url_suivante = next(
                (l.get("url") for l in liens if l.get("relation") == "next"), None
            )
            page += 1

    except Exception as e:
        logger.error(f"Erreur parsing API santé département {departement} : {e}")
        if callback:
            callback(f"  ✗ Erreur parsing : {e}")

    return pharmacies


# ─── SOURCE 2 : Pages Jaunes ───────────────────────────────────────────────────

def scraper_pages_jaunes_ville(ville: str, code_postal: str) -> List[Dict[str, Any]]:
    """Scrape Pages Jaunes pour les pharmacies d'une ville."""
    terme_lieu = f"{ville.replace(' ', '-')}-{code_postal}"
    url = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=pharmacie&ou={terme_lieu}"

    pharmacies = []
    resp = _get(url, _headers_web())
    if not resp:
        return pharmacies

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # Sélecteurs Pages Jaunes (plusieurs formats possibles)
        fiches = (
            soup.select("article.bi-generic")
            or soup.select("li.bi-item")
            or soup.select("[data-bi-name]")
        )

        for fiche in fiches:
            nom_el = (
                fiche.select_one(".bi-denomination")
                or fiche.select_one("h3.bi-denomination")
                or fiche.select_one(".denomination-base")
            )
            if not nom_el:
                continue
            nom = nom_el.get_text(strip=True)
            if not nom:
                continue

            adresse_el = fiche.select_one(".bi-address, .adresse")
            adresse = adresse_el.get_text(strip=True) if adresse_el else None

            tel_el = fiche.select_one("[data-phone], .bi-phone")
            telephone = None
            if tel_el:
                telephone = tel_el.get("data-phone") or tel_el.get_text(strip=True)

            email_el = fiche.select_one("a[href^='mailto:']")
            email = None
            if email_el:
                email = email_el.get("href", "").replace("mailto:", "").strip()

            pharmacies.append({
                "nom": nom,
                "adresse": adresse,
                "ville": ville.title(),
                "code_postal": code_postal,
                "telephone": telephone,
                "email": email,
                "source": "scraping_pagesjaunes",
            })

    except Exception as e:
        logger.error(f"Erreur Pages Jaunes {ville} : {e}")

    return pharmacies


# ─── ORCHESTRATEUR ──────────────────────────────────────────────────────────────

def scraper_departement(
    db_path: str,
    departement: str,
    callback: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[list] = None,
) -> Dict[str, int]:
    """
    Scrape toutes les pharmacies d'un département.
    Combine API annuaire santé + Pages Jaunes sur les villes trouvées.
    """
    compteurs = {"inserees": 0, "doublons": 0, "erreurs": 0}

    def log(msg: str):
        logger.info(msg)
        if callback:
            callback(msg)

    log(f"Démarrage scraping — Département {departement}")

    if stop_flag and stop_flag[0]:
        return compteurs

    # ── Étape 1 : API annuaire santé ──
    pharmacies_api = scraper_api_sante_departement(departement, callback=log)
    log(f"  API santé : {len(pharmacies_api)} pharmacies récupérées")

    # ── Étape 2 : Pages Jaunes sur les villes trouvées ──
    villes_vues = set()
    pharmacies_pj = []

    for p in pharmacies_api:
        ville = p.get("ville", "")
        cp = p.get("code_postal", "")
        if ville and cp and ville not in villes_vues:
            villes_vues.add(ville)
            if stop_flag and stop_flag[0]:
                break
            time.sleep(random.uniform(1.5, 2.5))
            log(f"  → Pages Jaunes : {ville} ({cp})")
            pj = scraper_pages_jaunes_ville(ville, cp)
            pharmacies_pj.extend(pj)

    log(f"  Pages Jaunes : {len(pharmacies_pj)} pharmacies récupérées")

    # ── Fusion et dédoublonnage inter-sources ──
    toutes = pharmacies_api + pharmacies_pj
    vus: set = set()
    uniques = []
    for p in toutes:
        cle = (p.get("nom", "").lower().strip(), str(p.get("code_postal", "")))
        if cle[0] and cle not in vus:
            vus.add(cle)
            p.setdefault("departement", departement)
            uniques.append(p)

    log(f"  Total après dédoublonnage : {len(uniques)} pharmacies uniques")

    # ── Insertion en base ──
    for pharm in uniques:
        if stop_flag and stop_flag[0]:
            break
        try:
            if pharmacie_existe(
                db_path,
                pharm.get("nom", ""),
                pharm.get("ville", ""),
                pharm.get("code_postal", ""),
            ):
                compteurs["doublons"] += 1
            else:
                result = inserer_pharmacie(db_path, pharm)
                if result:
                    compteurs["inserees"] += 1
                else:
                    compteurs["doublons"] += 1
        except Exception as e:
            compteurs["erreurs"] += 1
            logger.error(f"Erreur insertion {pharm.get('nom')} : {e}")

    log(
        f"Département {departement} terminé : "
        f"{compteurs['inserees']} insérées | "
        f"{compteurs['doublons']} doublons | "
        f"{compteurs['erreurs']} erreurs"
    )
    return compteurs
