"""
Scraper de parapharmacies françaises par département.

Sources :
  1. Overpass API (OpenStreetMap) — shop=chemist + shop=cosmetics
  2. Pages Jaunes — recherche par département, termes multiples, pagination
"""

import logging
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

# Termes Pages Jaunes — parapharmacies uniquement (pas les grandes enseignes)
PJ_TERMES = [
    "parapharmacie",
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


def _get(url: str, headers: dict = None, timeout: int = 25) -> Optional[requests.Response]:
    if headers is None:
        headers = {"User-Agent": _ua(), "Accept-Language": "fr-FR,fr;q=0.9"}
    for tentative in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
            if resp.status_code in (429, 503):
                time.sleep(8 * (tentative + 1))
                continue
            return resp if resp.status_code == 200 else None
        except requests.exceptions.Timeout:
            time.sleep(3 * (tentative + 1))
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connexion échouée {url[:60]} : {e}")
            time.sleep(3 * (tentative + 1))
        except Exception as e:
            logger.error(f"Erreur GET {url[:60]} : {e}")
            return None
    return None


def _dans_france(lat: float, lon: float) -> bool:
    """Vérifie que les coordonnées sont en France (métropole + DOM)."""
    return 41.0 <= lat <= 52.0 and -6.0 <= lon <= 10.0


# ─────────────────────────────────────────────────────────────────────────────
# Nom du département via geo.api.gouv.fr
# ─────────────────────────────────────────────────────────────────────────────

def _get_nom_departement(departement: str) -> str:
    """Retourne le nom officiel du département (ex: '42' → 'Loire')."""
    try:
        resp = requests.get(
            f"https://geo.api.gouv.fr/departements/{departement}",
            timeout=8, verify=False, headers={"User-Agent": _ua()}
        )
        if resp.status_code == 200:
            return resp.json().get("nom", "")
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1 : Overpass / OpenStreetMap
# ─────────────────────────────────────────────────────────────────────────────

def scraper_overpass(departement: str, callback=None) -> List[Dict[str, Any]]:
    """
    Récupère les parapharmacies via OpenStreetMap.
    Tags : shop=chemist (parapharmacies indépendantes) + shop=cosmetics (grandes enseignes).
    Filtrage GPS pour rester en France.
    """
    prefixe = _prefixe_cp(departement)

    query = (
        f'[out:json][timeout:90];'
        f'('
        f'node[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f'way[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f'relation[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f');'
        f'out center;'
    )
    query_enc = urllib.parse.quote(query)

    if callback:
        callback(f"  [OpenStreetMap] Dept {departement} (chemist + cosmetics)...")

    resp = None
    for mirror in OVERPASS_MIRRORS:
        url = f"{mirror}?data={query_enc}"
        if callback:
            callback(f"  [OpenStreetMap] Miroir {mirror.split('/')[2]}...")
        resp = _get(url, timeout=100)
        if resp is not None:
            if callback:
                callback(f"  [OpenStreetMap] OK : {mirror.split('/')[2]}")
            break
        time.sleep(2)

    if resp is None:
        if callback:
            callback("  [OpenStreetMap] Tous les miroirs indisponibles.")
        return []

    resultats = []
    try:
        data = resp.json()
        elements = data.get("elements", [])
        if callback:
            callback(f"  [OpenStreetMap] {len(elements)} éléments bruts")

        for el in elements:
            # Filtrage géographique France
            if el.get("type") == "node":
                lat, lon = el.get("lat", 0), el.get("lon", 0)
            else:
                center = el.get("center", {})
                lat, lon = center.get("lat", 0), center.get("lon", 0)
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
            adresse = f"{tags.get('addr:housenumber', '')} {tags.get('addr:street', '')}".strip() or None
            telephone = _nettoyer_tel(tags.get("phone") or tags.get("contact:phone") or "")
            email = tags.get("email") or tags.get("contact:email") or ""

            resultats.append({
                "nom": nom,
                "adresse": adresse,
                "ville": ville or None,
                "code_postal": cp,
                "departement": departement,
                "telephone": telephone or None,
                "email": email or None,
                "source": "scraping_osm",
            })

        if callback:
            callback(f"  [OpenStreetMap] {len(resultats)} parapharmacies en France")

    except Exception as e:
        logger.error(f"Erreur parsing Overpass dept {departement} : {e}")
        if callback:
            callback(f"  [OpenStreetMap] Erreur parsing : {e}")

    return resultats


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2 : Pages Jaunes — par département, termes multiples, pagination
# ─────────────────────────────────────────────────────────────────────────────

def _scraper_pj_url(url: str, departement: str, code_postal_prefixe: str) -> List[Dict[str, Any]]:
    """Parse une page de résultats Pages Jaunes et retourne les fiches."""
    headers = {
        "User-Agent": _ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Referer": "https://www.pagesjaunes.fr/",
    }
    resp = _get(url, headers=headers, timeout=25)
    if not resp:
        return []

    resultats = []
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        fiches = (
            soup.select("article.bi-generic")
            or soup.select("li.bi-item")
            or soup.select("[data-bi-id]")
            or soup.select(".bi-content")
        )

        for fiche in fiches:
            nom_el = (
                fiche.select_one(".bi-denomination")
                or fiche.select_one("h3")
                or fiche.select_one(".denomination-base")
                or fiche.select_one("[itemprop='name']")
            )
            if not nom_el:
                continue
            nom = _nettoyer_nom(nom_el.get_text(strip=True))
            if not nom:
                continue

            # Téléphone
            tel_el = fiche.select_one("[data-phone]")
            telephone = _nettoyer_tel(tel_el.get("data-phone", "") if tel_el else "")
            if not telephone:
                for sel in (".bi-phone", ".phone", "[itemprop='telephone']"):
                    t = fiche.select_one(sel)
                    if t:
                        telephone = _nettoyer_tel(t.get_text(strip=True))
                        break

            # Email
            email_el = fiche.select_one("a[href^='mailto:']")
            email = email_el.get("href", "").replace("mailto:", "").strip() if email_el else ""

            # Adresse
            adresse_el = fiche.select_one(".bi-address, .adresse, .street-address, [itemprop='streetAddress']")
            adresse = adresse_el.get_text(strip=True) if adresse_el else None

            # Code postal + ville depuis l'adresse ou le markup
            cp = ""
            ville = ""
            cp_el = fiche.select_one("[itemprop='postalCode']")
            ville_el = fiche.select_one("[itemprop='addressLocality']")
            if cp_el:
                cp = cp_el.get_text(strip=True)
            if ville_el:
                ville = ville_el.get_text(strip=True).title()

            # Fallback : extraire CP depuis texte adresse
            if not cp and adresse:
                import re
                m = re.search(r'\b(\d{5})\b', adresse)
                if m:
                    cp = m.group(1)

            # Garder seulement si CP correspond au département
            if cp and not cp.startswith(code_postal_prefixe):
                continue

            resultats.append({
                "nom": nom,
                "adresse": adresse,
                "ville": ville or None,
                "code_postal": cp or None,
                "departement": departement,
                "telephone": telephone or None,
                "email": email or None,
                "source": "scraping_pagesjaunes",
            })

    except Exception as e:
        logger.error(f"Erreur parsing PJ : {e}")

    return resultats


def scraper_pages_jaunes_departement(
    departement: str,
    nom_departement: str,
    terme: str,
    callback=None,
) -> List[Dict[str, Any]]:
    """
    Scrape Pages Jaunes pour un département entier avec un terme donné.
    Gère la pagination (jusqu'à 5 pages).
    """
    prefixe = _prefixe_cp(departement)
    ou = urllib.parse.quote(f"{nom_departement} ({departement})")
    terme_enc = urllib.parse.quote(terme)
    base_url = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui={terme_enc}&ou={ou}"

    resultats = []
    for page in range(1, 6):
        url = base_url if page == 1 else f"{base_url}&page={page}"
        fiches = _scraper_pj_url(url, departement, prefixe)
        if not fiches:
            break
        resultats.extend(fiches)
        if callback and fiches:
            callback(f"  [Pages Jaunes] {terme} — page {page} : {len(fiches)} fiches")
        time.sleep(random.uniform(1.5, 2.5))

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
    sans_cp = []
    for p in items:
        nom_norm = p.get("nom", "").lower().strip()
        cp = str(p.get("code_postal") or "").strip()
        if not nom_norm:
            continue
        if not cp:
            sans_cp.append(p)
            continue
        cle = (nom_norm, cp)
        if cle in index:
            index[cle] = _fusionner(index[cle], p)
        else:
            index[cle] = p
    return list(index.values()) + sans_cp


# ─────────────────────────────────────────────────────────────────────────────
# Test de connexion
# ─────────────────────────────────────────────────────────────────────────────

def _tester_connexion() -> bool:
    try:
        resp = requests.get("https://www.google.com", timeout=8, verify=False,
                            headers={"User-Agent": _ua()})
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATEUR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def scraper_departement(
    db_path: str,
    departement: str,
    callback: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[list] = None,
) -> Dict[str, int]:
    """
    Scrape toutes les parapharmacies d'un département.
    Sources : OpenStreetMap + Pages Jaunes (par département, termes multiples).
    """
    compteurs = {"inserees": 0, "doublons": 0, "erreurs": 0}

    def log(msg: str):
        logger.info(msg)
        if callback:
            callback(msg)

    def arrete() -> bool:
        return bool(stop_flag and stop_flag[0])

    log("=" * 48)
    log(f"Scraping parapharmacies — Département {departement}")
    log("=" * 48)

    if not _tester_connexion():
        log("ERREUR : Pas d'accès Internet.")
        return compteurs
    log("Connexion Internet OK.")

    # Nom du département pour Pages Jaunes
    nom_dept = _get_nom_departement(departement)
    if nom_dept:
        log(f"Département : {nom_dept} ({departement})")
    else:
        nom_dept = departement

    toutes: List[Dict] = []

    # ── Source 1 : OpenStreetMap ───────────────────────────────────────────
    if not arrete():
        try:
            osm = scraper_overpass(departement, callback=log)
            toutes.extend(osm)
            log(f"  → OSM : {len(osm)} résultats")
        except Exception as e:
            log(f"  [OSM] Erreur : {e}")

    # ── Source 2 : Pages Jaunes — tous les termes ──────────────────────────
    if not arrete():
        log(f"  [Pages Jaunes] Recherche sur {len(PJ_TERMES)} termes...")
        for terme in PJ_TERMES:
            if arrete():
                break
            try:
                pj = scraper_pages_jaunes_departement(departement, nom_dept, terme, callback=log)
                if pj:
                    toutes.extend(pj)
                    log(f"  → PJ '{terme}' : {len(pj)} résultats")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                log(f"  [PJ] Erreur '{terme}' : {e}")

    log(f"Total brut : {len(toutes)}")
    uniques = _dedoublonner(toutes)
    log(f"Après dédoublonnage : {len(uniques)} parapharmacies uniques")

    if not uniques:
        log("Aucune parapharmacie trouvée pour ce département.")
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

    log("=" * 48)
    log(
        f"TERMINÉ — {compteurs['inserees']} insérées | "
        f"{compteurs['doublons']} doublons | "
        f"{compteurs['erreurs']} erreurs"
    )
    log("=" * 48)
    return compteurs
