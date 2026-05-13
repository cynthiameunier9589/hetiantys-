"""
Scraper de parapharmacies françaises par département.

Sources :
  1. Overpass API (OpenStreetMap) — données fiables, publiques, ~70% de couverture
  2. Pages Jaunes — complément et enrichissement email/téléphone
"""

import logging
import time
import random
import urllib.parse
from typing import Callable, Optional, List, Dict, Any

import requests
import urllib3
from bs4 import BeautifulSoup

# Désactive les avertissements SSL pour Mac Python 3.9 / LibreSSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from database import inserer_pharmacie, pharmacie_existe

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

# Plusieurs miroirs Overpass pour la redondance
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
    """Préfixe de code postal pour un département (gère 2A, 2B, DOM)."""
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
    """GET robuste avec retry, SSL désactivé (Mac LibreSSL)."""
    if headers is None:
        headers = {"User-Agent": _ua(), "Accept-Language": "fr-FR,fr;q=0.9"}
    for tentative in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
            if resp.status_code in (429, 503):
                wait = 6 * (tentative + 1)
                logger.warning(f"HTTP {resp.status_code} — attente {wait}s")
                time.sleep(wait)
                continue
            logger.debug(f"GET {url} → HTTP {resp.status_code}")
            return resp if resp.status_code == 200 else None
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout {url} (tentative {tentative + 1})")
            time.sleep(3 * (tentative + 1))
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connexion {url} (tentative {tentative + 1}) : {e}")
            time.sleep(3 * (tentative + 1))
        except Exception as e:
            logger.error(f"Erreur {url} : {e}")
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1 : Overpass / OpenStreetMap
# ─────────────────────────────────────────────────────────────────────────────

def scraper_overpass(departement: str, callback=None) -> List[Dict[str, Any]]:
    """
    Récupère les pharmacies via l'API OpenStreetMap (Overpass).
    Utilise GET (plus fiable que POST) avec plusieurs miroirs.
    """
    prefixe = _prefixe_cp(departement)

    # Requête Overpass en GET (encodage URL)
    # shop=chemist est le tag OSM pour les parapharmacies en France
    query = (
        f'[out:json][timeout:60];'
        f'('
        f'node[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f'way[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f'relation[shop=chemist]["addr:postcode"~"^{prefixe}"];'
        f'node[amenity=pharmacy][name~"parapharmacie",i]["addr:postcode"~"^{prefixe}"];'
        f'way[amenity=pharmacy][name~"parapharmacie",i]["addr:postcode"~"^{prefixe}"];'
        f');'
        f'out center;'
    )
    query_enc = urllib.parse.quote(query)

    if callback:
        callback(f"  [OpenStreetMap] Parapharmacies departement {departement}...")

    resp = None
    for mirror in OVERPASS_MIRRORS:
        url = f"{mirror}?data={query_enc}"
        resp = _get(url, timeout=70)
        if resp is not None:
            if callback:
                callback(f"  [OpenStreetMap] Miroir OK : {mirror.split('/')[2]}")
            break
        if callback:
            callback(f"  [OpenStreetMap] Miroir {mirror.split('/')[2]} indisponible, essai suivant...")
        time.sleep(2)

    if resp is None:
        if callback:
            callback(f"  [OpenStreetMap] Tous les miroirs indisponibles.")
        return []

    pharmacies = []
    try:
        data = resp.json()
        elements = data.get("elements", [])

        if callback:
            callback(f"  [OpenStreetMap] {len(elements)} elements trouves")

        for el in elements:
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
            num = tags.get("addr:housenumber", "")
            rue = tags.get("addr:street", "")
            adresse = f"{num} {rue}".strip() or None

            telephone = _nettoyer_tel(
                tags.get("phone") or tags.get("contact:phone") or ""
            )
            email = tags.get("email") or tags.get("contact:email") or ""

            pharmacies.append({
                "nom": nom,
                "adresse": adresse,
                "ville": ville or None,
                "code_postal": cp,
                "departement": departement,
                "telephone": telephone or None,
                "email": email or None,
                "source": "scraping_data_gouv",
            })

        if callback:
            callback(f"  [OpenStreetMap] {len(pharmacies)} parapharmacies extraites")

    except Exception as e:
        logger.error(f"Erreur parsing Overpass dept {departement} : {e}")
        if callback:
            callback(f"  [OpenStreetMap] Erreur parsing : {e}")

    return pharmacies


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2 : Pages Jaunes
# ─────────────────────────────────────────────────────────────────────────────

def scraper_pages_jaunes(ville: str, code_postal: str, callback=None) -> List[Dict[str, Any]]:
    """Scrape Pages Jaunes pour enrichir une ville (emails/téléphones)."""
    ville_url = urllib.parse.quote(f"{ville} {code_postal}")
    url = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=parapharmacie&ou={ville_url}"

    headers = {
        "User-Agent": _ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Referer": "https://www.pagesjaunes.fr/",
    }

    resp = _get(url, headers=headers, timeout=20)
    if not resp:
        return []

    pharmacies = []
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
            )
            if not nom_el:
                continue
            nom = _nettoyer_nom(nom_el.get_text(strip=True))
            if not nom:
                continue

            tel_el = fiche.select_one("[data-phone]")
            telephone = _nettoyer_tel(tel_el.get("data-phone", "") if tel_el else "")
            if not telephone:
                tel_el2 = fiche.select_one(".bi-phone, .phone")
                if tel_el2:
                    telephone = _nettoyer_tel(tel_el2.get_text(strip=True))

            email_el = fiche.select_one("a[href^='mailto:']")
            email = email_el.get("href", "").replace("mailto:", "").strip() if email_el else ""

            adresse_el = fiche.select_one(".bi-address, .adresse, .street-address")
            adresse = adresse_el.get_text(strip=True) if adresse_el else None

            pharmacies.append({
                "nom": nom,
                "adresse": adresse,
                "ville": ville.title(),
                "code_postal": code_postal,
                "telephone": telephone or None,
                "email": email or None,
                "source": "scraping_pagesjaunes",
            })

    except Exception as e:
        logger.error(f"Erreur Pages Jaunes {ville} : {e}")

    return pharmacies


# ─────────────────────────────────────────────────────────────────────────────
# Fusion et dédoublonnage
# ─────────────────────────────────────────────────────────────────────────────

def _fusionner(base: Dict, complement: Dict) -> Dict:
    """Complète les champs vides de base avec ceux de complement."""
    result = dict(base)
    for cle in ("adresse", "ville", "telephone", "email"):
        if not result.get(cle) and complement.get(cle):
            result[cle] = complement[cle]
    return result


def _dedoublonner(pharmacies: List[Dict]) -> List[Dict]:
    """Dédoublonne par (nom normalisé + code postal) en fusionnant."""
    index: Dict[tuple, Dict] = {}
    for p in pharmacies:
        nom_norm = p.get("nom", "").lower().strip()
        cp = str(p.get("code_postal", "")).strip()
        if not nom_norm or not cp:
            continue
        cle = (nom_norm, cp)
        if cle in index:
            index[cle] = _fusionner(index[cle], p)
        else:
            index[cle] = p
    return list(index.values())


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATEUR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def _tester_connexion(callback=None) -> bool:
    """Vérifie qu'Internet est accessible depuis Python/requests."""
    url_test = "https://www.google.com"
    try:
        resp = requests.get(url_test, timeout=8, verify=False,
                            headers={"User-Agent": _ua()})
        return resp.status_code == 200
    except Exception as e:
        if callback:
            callback(f"  Test connexion echoue : {e}")
        return False


def scraper_departement(
    db_path: str,
    departement: str,
    callback: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[list] = None,
) -> Dict[str, int]:
    """
    Scrape toutes les pharmacies d'un département.
    Sources : OpenStreetMap (principal) + Pages Jaunes (enrichissement).
    """
    compteurs = {"inserees": 0, "doublons": 0, "erreurs": 0}

    def log(msg: str):
        logger.info(msg)
        if callback:
            callback(msg)

    def arrete() -> bool:
        return bool(stop_flag and stop_flag[0])

    log("=" * 44)
    log(f"Scraping parapharmacies departement {departement}")
    log("=" * 44)

    # ── Test de connexion ──────────────────────────────────────────────────
    log("Test de connexion Internet...")
    if not _tester_connexion(callback=log):
        log("ERREUR : Pas d'acces Internet depuis Python.")
        log("Verifiez votre connexion WiFi/Ethernet.")
        return compteurs
    log("Connexion Internet OK.")

    toutes: List[Dict] = []

    # ── Source 1 : OpenStreetMap ───────────────────────────────────────────
    if not arrete():
        try:
            osm = scraper_overpass(departement, callback=log)
            toutes.extend(osm)
        except Exception as e:
            log(f"  [OpenStreetMap] Erreur inattendue : {e}")

    # ── Source 2 : Pages Jaunes sur toutes les villes trouvées ─────────────
    if not arrete() and toutes:
        villes = {}
        for p in toutes:
            v = p.get("ville", "")
            cp = p.get("code_postal", "")
            if v and cp and v not in villes:
                villes[v] = cp

        log(f"  [Pages Jaunes] Enrichissement sur {len(villes)} villes...")
        pj_total = []
        for i, (ville, cp) in enumerate(list(villes.items())[:30]):
            if arrete():
                break
            time.sleep(random.uniform(1.5, 2.5))
            pj = scraper_pages_jaunes(ville, cp, callback=None)
            pj_total.extend(pj)

        if pj_total:
            # Fusionner les données PJ dans les fiches OSM existantes
            index_pj = {}
            for p in pj_total:
                cle = (p.get("nom", "").lower().strip(), str(p.get("code_postal", "")))
                if cle[0]:
                    index_pj[cle] = p

            for i, pharm in enumerate(toutes):
                cle = (pharm.get("nom", "").lower().strip(), str(pharm.get("code_postal", "")))
                if cle in index_pj:
                    toutes[i] = _fusionner(pharm, index_pj[cle])

            # Ajouter les pharmacies PJ non trouvées dans OSM
            for p in pj_total:
                cle = (p.get("nom", "").lower().strip(), str(p.get("code_postal", "")))
                if cle[0] and cle not in {
                    (x.get("nom", "").lower().strip(), str(x.get("code_postal", "")))
                    for x in toutes
                }:
                    toutes.append(p)

            log(f"  [Pages Jaunes] Enrichissement applique ({len(pj_total)} fiches PJ)")

    log(f"Total brut : {len(toutes)} | Apres dedoublonnage : ", )
    uniques = _dedoublonner(toutes)
    log(f"  {len(uniques)} parapharmacies uniques")

    if not uniques:
        log("Aucune parapharmacie trouvee.")
        log("Causes possibles : WiFi absent, departement sans donnees OSM.")
        return compteurs

    # ── Insertion en base ──────────────────────────────────────────────────
    log(f"Insertion en base de donnees...")
    for pharm in uniques:
        if arrete():
            log("Scraping interrompu.")
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
                if inserer_pharmacie(db_path, pharm):
                    compteurs["inserees"] += 1
                else:
                    compteurs["doublons"] += 1
        except Exception as e:
            compteurs["erreurs"] += 1
            logger.error(f"Erreur insertion {pharm.get('nom')} : {e}")

    log("=" * 44)
    log(
        f"TERMINE — {compteurs['inserees']} inserees | "
        f"{compteurs['doublons']} doublons | "
        f"{compteurs['erreurs']} erreurs"
    )
    log("=" * 44)
    return compteurs
