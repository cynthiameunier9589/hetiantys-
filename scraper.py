"""
Scraper de parapharmacies françaises par département.

Source principale : API Annuaire Entreprises (recherche-entreprises.api.gouv.fr)
  — données officielles SIRENE, gratuite, sans clé API.
Source secondaire : Overpass / OpenStreetMap (shop=chemist).
"""

import json
import logging
import re
import time
import random
import urllib.parse
from typing import Callable, Optional, List, Dict, Any

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from database import inserer_pharmacie, pharmacie_existe

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

REGIONS_DEPARTEMENTS = {
    "Auvergne-Rhône-Alpes":       ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "Bourgogne-Franche-Comté":    ["21", "25", "39", "58", "70", "71", "89", "90"],
    "Bretagne":                   ["22", "29", "35", "56"],
    "Centre-Val de Loire":        ["18", "28", "36", "37", "41", "45"],
    "Corse":                      ["2A", "2B"],
    "Grand Est":                  ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "Hauts-de-France":            ["02", "59", "60", "62", "80"],
    "Île-de-France":              ["75", "77", "78", "91", "92", "93", "94", "95"],
    "Normandie":                  ["14", "27", "50", "61", "76"],
    "Nouvelle-Aquitaine":         ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "Occitanie":                  ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "Pays de la Loire":           ["44", "49", "53", "72", "85"],
    "Provence-Alpes-Côte d'Azur": ["04", "05", "06", "13", "83", "84"],
    "DOM-TOM":                    ["971", "972", "973", "974", "976"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ─────────────────────────────────────────────────────────────────────────────

def _prefixe_cp(departement: str) -> str:
    d = departement.upper().strip()
    if d in ("2A", "2B"):
        return d
    try:
        return str(int(d)).zfill(2)
    except ValueError:
        return d


def _ua() -> str:
    return random.choice(USER_AGENTS)


def _nettoyer_nom(s: str) -> str:
    return s.strip().title() if s else ""


def _nettoyer_tel(s: str) -> str:
    if not s:
        return ""
    t = s.strip().replace(" ", "").replace(".", "").replace("-", "")
    if t.startswith("+33"):
        t = "0" + t[3:]
    return t


def _get(url: str, params: dict = None, timeout: int = 20) -> Optional[requests.Response]:
    headers = {"User-Agent": _ua(), "Accept-Language": "fr-FR,fr;q=0.9"}
    for tentative in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers,
                                timeout=timeout, verify=False)
            if resp.status_code in (429, 503):
                time.sleep(8 * (tentative + 1))
                continue
            return resp if resp.status_code == 200 else None
        except requests.exceptions.Timeout:
            time.sleep(3 * (tentative + 1))
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connexion {url[:50]} : {e}")
            time.sleep(3 * (tentative + 1))
        except Exception as e:
            logger.error(f"Erreur {url[:50]} : {e}")
            return None
    return None


def _dans_france(lat: float, lon: float) -> bool:
    if lat == 0 and lon == 0:
        return False
    if 41.0 <= lat <= 52.0 and -6.0 <= lon <= 10.0:
        return True
    if 15.8 <= lat <= 16.6 and -61.9 <= lon <= -60.9:  # Guadeloupe
        return True
    if 14.3 <= lat <= 15.0 and -61.3 <= lon <= -60.7:  # Martinique
        return True
    if 2.0 <= lat <= 5.8 and -54.6 <= lon <= -51.5:    # Guyane
        return True
    if -21.5 <= lat <= -20.8 and 55.2 <= lon <= 55.9:  # Réunion
        return True
    if -13.1 <= lat <= -12.6 and 45.0 <= lon <= 45.4:  # Mayotte
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1 : API Annuaire Entreprises (gouvernement français — SIRENE)
# ─────────────────────────────────────────────────────────────────────────────

def scraper_annuaire_entreprises(departement: str, callback=None) -> List[Dict[str, Any]]:
    """
    Recherche les parapharmacies via l'API officielle Annuaire Entreprises.
    Données SIRENE — sans clé API, sans blocage.
    Filtre par siege.departement dans la réponse (plus fiable que paramètre URL).
    """
    base_url = "https://recherche-entreprises.api.gouv.fr/search"
    resultats = []

    # Deux termes de recherche pour maximiser la couverture
    termes = ["parapharmacie", "para pharmacie"]

    for terme in termes:
        if callback:
            callback(f"  [Annuaire] Recherche '{terme}' dept {departement}...")

        total_pages = 1
        for page in range(1, 50):
            try:
                resp = _get(base_url, params={
                    "q": terme,
                    "departement": departement,   # paramètre correct de l'API
                    "page": page,
                    "per_page": 25,
                }, timeout=20)

                if not resp:
                    break

                data = resp.json()
                total_pages = data.get("total_pages", 1)
                items = data.get("results", [])

                if not items:
                    break

                for item in items:
                    siege = item.get("siege", {})

                    # Filtrage par département depuis la réponse
                    dept_siege = str(siege.get("departement") or "").strip()
                    if dept_siege and dept_siege != departement:
                        continue

                    nom = _nettoyer_nom(
                        item.get("nom_raison_sociale") or item.get("nom_complet") or ""
                    )
                    if not nom:
                        continue

                    cp = str(siege.get("code_postal") or "").strip()
                    ville = _nettoyer_nom(siege.get("libelle_commune") or "")
                    adresse = siege.get("adresse") or None
                    telephone = _nettoyer_tel(siege.get("telephone") or "")

                    resultats.append({
                        "nom": nom,
                        "adresse": adresse,
                        "ville": ville or None,
                        "code_postal": cp or None,
                        "departement": departement,
                        "telephone": telephone or None,
                        "email": None,
                        "source": "annuaire_entreprises",
                    })

                if callback:
                    callback(f"  [Annuaire] Page {page}/{total_pages}")

                if page >= total_pages:
                    break

                time.sleep(0.4)

            except Exception as e:
                logger.error(f"Erreur Annuaire dept {departement} : {e}")
                break

    if callback:
        callback(f"  [Annuaire] Total brut : {len(resultats)} parapharmacies")

    return resultats


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2 : Overpass / OpenStreetMap (fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _overpass_post(query: str, timeout: int = 100) -> Optional[requests.Response]:
    headers = {"User-Agent": _ua(), "Content-Type": "application/x-www-form-urlencoded"}
    for mirror in OVERPASS_MIRRORS:
        for tentative in range(2):
            try:
                resp = requests.post(mirror, data={"data": query},
                                     headers=headers, timeout=timeout, verify=False)
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429:
                    time.sleep(10)
            except Exception:
                time.sleep(2)
                break
        time.sleep(2)
    return None


def scraper_overpass(departement: str, callback=None) -> List[Dict[str, Any]]:
    """Récupère les parapharmacies via OpenStreetMap (shop=chemist)."""
    prefixe = _prefixe_cp(departement)
    query = (
        f'[out:json][timeout:90];'
        f'(node[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f'way[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f'relation[shop=chemist]["addr:postcode"~"^{prefixe}"];);'
        f'out center;'
    )

    if callback:
        callback("  [OpenStreetMap] Envoi requête POST...")

    resp = _overpass_post(query)
    if resp is None:
        if callback:
            callback("  [OpenStreetMap] Indisponible (sera ignoré).")
        return []

    resultats = []
    try:
        elements = resp.json().get("elements", [])
        if callback:
            callback(f"  [OpenStreetMap] {len(elements)} éléments bruts")

        for el in elements:
            if el.get("type") == "node":
                lat, lon = el.get("lat", 0), el.get("lon", 0)
            else:
                c = el.get("center", {})
                lat, lon = c.get("lat", 0), c.get("lon", 0)
            if not _dans_france(lat, lon):
                continue

            tags = el.get("tags", {})
            nom = _nettoyer_nom(tags.get("name") or tags.get("operator") or "")
            if not nom:
                continue
            cp = (tags.get("addr:postcode") or "").strip()
            if not cp or not cp.startswith(prefixe):
                continue

            ville = _nettoyer_nom(
                tags.get("addr:city") or tags.get("addr:municipality")
                or tags.get("addr:town") or tags.get("addr:village") or ""
            )
            adresse = f"{tags.get('addr:housenumber','')} {tags.get('addr:street','')}".strip() or None
            telephone = _nettoyer_tel(tags.get("phone") or tags.get("contact:phone") or "")
            email = tags.get("email") or tags.get("contact:email") or ""

            resultats.append({
                "nom": nom, "adresse": adresse,
                "ville": ville or None, "code_postal": cp,
                "departement": departement,
                "telephone": telephone or None, "email": email or None,
                "source": "scraping_osm",
            })

        if callback:
            callback(f"  [OpenStreetMap] {len(resultats)} parapharmacies France")

    except Exception as e:
        logger.error(f"Erreur parsing OSM dept {departement} : {e}")

    return resultats


# ─────────────────────────────────────────────────────────────────────────────
# Fusion et dédoublonnage
# ─────────────────────────────────────────────────────────────────────────────

def _fusionner(base: Dict, complement: Dict) -> Dict:
    result = dict(base)
    for cle in ("adresse", "ville", "code_postal", "telephone", "email"):
        if not result.get(cle) and complement.get(cle):
            result[cle] = complement[cle]
    return result


def _dedoublonner(items: List[Dict]) -> List[Dict]:
    index: Dict[tuple, Dict] = {}
    for p in items:
        nom_norm = p.get("nom", "").lower().strip()
        if not nom_norm:
            continue
        cp = str(p.get("code_postal") or "").strip()
        ville_norm = (p.get("ville") or "").lower().strip()
        cle = (nom_norm, cp) if cp else (nom_norm, ville_norm)
        if cle in index:
            index[cle] = _fusionner(index[cle], p)
        else:
            index[cle] = p
    return list(index.values())


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATEUR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def _tester_connexion() -> bool:
    try:
        resp = requests.get("https://www.google.com", timeout=8, verify=False,
                            headers={"User-Agent": _ua()})
        return resp.status_code == 200
    except Exception:
        return False


def scraper_departement(
    db_path: str,
    departement: str,
    callback: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[list] = None,
) -> Dict[str, int]:
    """
    Scrape toutes les parapharmacies d'un département.
    Source principale : API Annuaire Entreprises (gouvernement FR).
    Source secondaire : OpenStreetMap.
    """
    compteurs = {"inserees": 0, "doublons": 0, "erreurs": 0}

    def log(msg: str):
        logger.info(msg)
        if callback:
            callback(msg)

    def arrete() -> bool:
        return bool(stop_flag and stop_flag[0])

    log("=" * 50)
    log(f"Scraping parapharmacies — Département {departement}")
    log("=" * 50)

    if not _tester_connexion():
        log("ERREUR : Pas d'accès Internet.")
        return compteurs
    log("Connexion Internet OK.")

    toutes: List[Dict] = []

    # ── Source 1 : API Annuaire Entreprises (principale) ──────────────────
    if not arrete():
        try:
            annuaire = scraper_annuaire_entreprises(departement, callback=log)
            toutes.extend(annuaire)
            log(f"  → Annuaire officiel : {len(annuaire)} résultats")
        except Exception as e:
            log(f"  [Annuaire] Erreur : {e}")

    # ── Source 2 : OpenStreetMap (complément) ─────────────────────────────
    if not arrete():
        try:
            osm = scraper_overpass(departement, callback=log)
            if osm:
                toutes.extend(osm)
                log(f"  → OpenStreetMap : {len(osm)} résultats")
        except Exception as e:
            log(f"  [OSM] Erreur : {e}")

    log(f"Total brut : {len(toutes)}")
    uniques = _dedoublonner(toutes)
    log(f"Après dédoublonnage : {len(uniques)} parapharmacies uniques")

    if not uniques:
        log("Aucune parapharmacie trouvée pour ce département.")
        log("Vérifiez votre connexion Internet.")
        return compteurs

    # ── Insertion en base ──────────────────────────────────────────────────
    log("Insertion en base de données...")
    for pharm in uniques:
        if arrete():
            log("Scraping interrompu.")
            break
        try:
            pharm.setdefault("departement", departement)
            if pharmacie_existe(
                db_path,
                pharm.get("nom", ""),
                pharm.get("ville", "") or "",
                pharm.get("code_postal", "") or "",
            ):
                compteurs["doublons"] += 1
            else:
                if inserer_pharmacie(db_path, pharm):
                    compteurs["inserees"] += 1
                else:
                    compteurs["doublons"] += 1
        except Exception as e:
            compteurs["erreurs"] += 1
            logger.error(f"Erreur insertion {pharm.get('nom')} : {e}")

    log("=" * 50)
    log(
        f"TERMINÉ — {compteurs['inserees']} insérées | "
        f"{compteurs['doublons']} doublons | "
        f"{compteurs['erreurs']} erreurs"
    )
    log("=" * 50)
    return compteurs
