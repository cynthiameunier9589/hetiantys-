"""
Module de scraping des pharmacies par région/département.
Sources : API annuaire santé (data.gouv) + Pages Jaunes.
"""

import logging
import time
import random
import re
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36",
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


def _headers_aleatoires() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def _requete_avec_retry(url: str, max_tentatives: int = 3, delai_base: float = 2.0) -> Optional[requests.Response]:
    """Effectue une requête HTTP avec retry exponentiel sur erreur 429/503."""
    for tentative in range(max_tentatives):
        try:
            resp = requests.get(url, headers=_headers_aleatoires(), timeout=15)
            if resp.status_code in (429, 503):
                attente = delai_base * (2 ** tentative) + random.uniform(0, 1)
                logger.warning(f"Erreur {resp.status_code} sur {url}, attente {attente:.1f}s")
                time.sleep(attente)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout sur {url} (tentative {tentative + 1})")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Erreur réseau sur {url} (tentative {tentative + 1})")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Erreur HTTP {e} sur {url}")
            break
        if tentative < max_tentatives - 1:
            time.sleep(delai_base * (2 ** tentative))
    return None


# ─── SOURCE 1 : API Annuaire Santé ─────────────────────────────────────────────

def scraper_api_sante(code_postal: str) -> List[Dict[str, Any]]:
    """
    Interroge l'API FHIR de l'annuaire santé pour les pharmacies d'un code postal.
    Source officielle, 0 risque de blocage.
    """
    url = (
        f"https://api.annuaire.sante.fr/fhir/v1/Organization"
        f"?type=PHAR&address-postalcode={code_postal}&_count=100"
    )
    pharmacies = []

    resp = _requete_avec_retry(url)
    if not resp:
        return pharmacies

    try:
        data = resp.json()
        entrees = data.get("entry", [])
        for entree in entrees:
            resource = entree.get("resource", {})
            nom = resource.get("name", "")
            if not nom:
                continue

            adresse_data = (resource.get("address") or [{}])[0]
            adresse = " ".join(adresse_data.get("line", []))
            ville = adresse_data.get("city", "")
            cp = adresse_data.get("postalCode", code_postal)

            telecom = resource.get("telecom", [])
            telephone = next(
                (t["value"] for t in telecom if t.get("system") == "phone"), ""
            )

            pharmacies.append({
                "nom": nom.title(),
                "adresse": adresse or None,
                "ville": ville.title() if ville else None,
                "code_postal": cp or None,
                "telephone": telephone or None,
                "source": "scraping_data_gouv",
            })
    except Exception as e:
        logger.error(f"Erreur parsing API santé pour {code_postal} : {e}")

    return pharmacies


# ─── SOURCE 2 : Pages Jaunes ───────────────────────────────────────────────────

def scraper_pages_jaunes(ville: str, code_postal: str) -> List[Dict[str, Any]]:
    """Scrape Pages Jaunes pour les pharmacies d'une ville/code postal."""
    terme_lieu = f"{ville}+{code_postal}".replace(" ", "+")
    url = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=pharmacie&ou={terme_lieu}"

    pharmacies = []
    resp = _requete_avec_retry(url)
    if not resp:
        return pharmacies

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        fiches = soup.select("article.bi-generic, div.bi-content, li.bi-item")

        if not fiches:
            # Structure alternative Pages Jaunes
            fiches = soup.select("[data-bi-name]")

        for fiche in fiches:
            nom_el = fiche.select_one(".bi-denomination, .denomination-base, h3.bi-denomination")
            if not nom_el:
                continue
            nom = nom_el.get_text(strip=True)

            adresse_el = fiche.select_one(".bi-address, .adresse")
            adresse = adresse_el.get_text(strip=True) if adresse_el else None

            tel_el = fiche.select_one(".bi-phone, [data-phone]")
            telephone = None
            if tel_el:
                telephone = tel_el.get("data-phone") or tel_el.get_text(strip=True)

            email_el = fiche.select_one("a[href^='mailto:']")
            email = None
            if email_el:
                href = email_el.get("href", "")
                email = href.replace("mailto:", "").strip()

            pharmacies.append({
                "nom": nom,
                "adresse": adresse,
                "ville": ville.title() if ville else None,
                "code_postal": code_postal,
                "telephone": telephone,
                "email": email,
                "source": "scraping_pagesjaunes",
            })

    except Exception as e:
        logger.error(f"Erreur scraping PJ pour {ville} {code_postal} : {e}")

    return pharmacies


# ─── ORCHESTRATEUR ──────────────────────────────────────────────────────────────

def scraper_departement(
    db_path: str,
    departement: str,
    callback: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[list] = None,
) -> Dict[str, int]:
    """
    Scrape toutes les pharmacies d'un département depuis les deux sources.
    stop_flag est une liste d'un élément ; si stop_flag[0] == True, on arrête.
    """
    compteurs = {"inserees": 0, "doublons": 0, "erreurs": 0}

    def log(msg: str):
        logger.info(msg)
        if callback:
            callback(msg)

    # Codes postaux typiques pour le département (préfixe)
    prefixes_cp = _codes_postaux_par_departement(departement)
    log(f"Démarrage scraping département {departement} ({len(prefixes_cp)} codes postaux)")

    villes_traitees = set()

    for cp in prefixes_cp:
        if stop_flag and stop_flag[0]:
            log("Scraping interrompu par l'utilisateur.")
            break

        log(f"  → API santé : code postal {cp}")
        pharmacies_api = scraper_api_sante(cp)

        pharmacies_pj = []
        villes = list({p["ville"] for p in pharmacies_api if p.get("ville")})
        for ville in villes:
            if ville in villes_traitees:
                continue
            villes_traitees.add(ville)
            time.sleep(random.uniform(2, 3))
            log(f"  → Pages Jaunes : {ville} {cp}")
            pharmacies_pj.extend(scraper_pages_jaunes(ville, cp))

        # Fusion et dédoublonnage
        toutes = pharmacies_api + pharmacies_pj
        vus = set()
        uniques = []
        for p in toutes:
            cle = (p.get("nom", "").lower().strip(), p.get("code_postal", ""))
            if cle not in vus and cle[0]:
                vus.add(cle)
                uniques.append(p)

        for pharm in uniques:
            pharm.setdefault("departement", departement)
            try:
                if pharmacie_existe(
                    db_path,
                    pharm.get("nom", ""),
                    pharm.get("ville", ""),
                    pharm.get("code_postal", ""),
                ):
                    compteurs["doublons"] += 1
                else:
                    inserer_pharmacie(db_path, pharm)
                    compteurs["inserees"] += 1
            except Exception as e:
                compteurs["erreurs"] += 1
                logger.error(f"Erreur insertion {pharm.get('nom')} : {e}")

    log(
        f"Département {departement} terminé : "
        f"{compteurs['inserees']} insérées, "
        f"{compteurs['doublons']} doublons, "
        f"{compteurs['erreurs']} erreurs"
    )
    return compteurs


def _codes_postaux_par_departement(dpt: str) -> List[str]:
    """Génère une liste de codes postaux représentatifs pour un département."""
    if dpt in ("2A",):
        return ["20000", "20090", "20100", "20111", "20130", "20160", "20200"]
    if dpt in ("2B",):
        return ["20200", "20212", "20213", "20220", "20230", "20250", "20600"]

    try:
        num = int(dpt)
        # Pour les DOM
        if num in (971, 972, 973, 974, 976):
            prefixe = str(num)
            return [f"{prefixe}{str(i).zfill(2)}" for i in range(0, 10)]
        # Pour la métropole : générer une sélection de codes postaux
        prefixe = dpt.zfill(2)
        codes = []
        # Codes principaux (ville principale + communes)
        for suffixe in range(0, 1000, 100):
            codes.append(f"{prefixe}{str(suffixe).zfill(3)}")
        return codes[:15]  # Limite raisonnable
    except ValueError:
        return [dpt + "000"]
