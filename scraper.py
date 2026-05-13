"""
Scraper de pharmacies françaises par département.

Sources combinées (par ordre de fiabilité) :
  1. API Annuaire Santé FHIR (type=SA25) — données officielles, complètes
  2. Overpass API / OpenStreetMap — couverture complémentaire ~70%
  3. Pages Jaunes — enrichissement email/téléphone

Aucune source ne bloque les requêtes si on respecte les délais polis.
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
    "Auvergne-Rhône-Alpes":     ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "Bourgogne-Franche-Comté":  ["21", "25", "39", "58", "70", "71", "89", "90"],
    "Bretagne":                 ["22", "29", "35", "56"],
    "Centre-Val de Loire":      ["18", "28", "36", "37", "41", "45"],
    "Corse":                    ["2A", "2B"],
    "Grand Est":                ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "Hauts-de-France":          ["02", "59", "60", "62", "80"],
    "Ile-de-France":            ["75", "77", "78", "91", "92", "93", "94", "95"],
    "Normandie":                ["14", "27", "50", "61", "76"],
    "Nouvelle-Aquitaine":       ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "Occitanie":                ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "Pays de la Loire":         ["44", "49", "53", "72", "85"],
    "Provence-Alpes-Côte d'Azur": ["04", "05", "06", "13", "83", "84"],
    "DOM-TOM":                  ["971", "972", "973", "974", "976"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires réseau
# ─────────────────────────────────────────────────────────────────────────────

def _get(url: str, headers: dict, timeout: int = 30, params: dict = None) -> Optional[requests.Response]:
    """GET robuste avec retry sur 429/503 et timeout."""
    for tentative in range(4):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code in (429, 503):
                attente = 5 * (tentative + 1)
                logger.warning(f"HTTP {resp.status_code} — attente {attente}s")
                time.sleep(attente)
                continue
            if resp.status_code == 200:
                return resp
            logger.warning(f"HTTP {resp.status_code} pour {url}")
            return None
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout {url} (tentative {tentative + 1})")
            time.sleep(2 * (tentative + 1))
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connexion impossible {url}")
            return None
        except Exception as e:
            logger.error(f"Erreur {url} : {e}")
            return None
    return None


def _post(url: str, data: dict, timeout: int = 60) -> Optional[requests.Response]:
    """POST robuste (utilisé pour Overpass)."""
    try:
        resp = requests.post(
            url, data=data,
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=timeout
        )
        if resp.status_code == 200:
            return resp
        return None
    except Exception as e:
        logger.error(f"Erreur POST {url} : {e}")
        return None


def _nettoyer_nom(nom: str) -> str:
    """Normalise le nom d'une pharmacie."""
    return nom.strip().title() if nom else ""


def _nettoyer_tel(tel: str) -> str:
    """Normalise un numéro de téléphone."""
    if not tel:
        return ""
    tel = tel.strip().replace(" ", "").replace(".", "").replace("-", "")
    if tel.startswith("+33"):
        tel = "0" + tel[3:]
    return tel


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 1 : API Annuaire Santé FHIR (officielle, complète)
# ─────────────────────────────────────────────────────────────────────────────

def _prefixe_cp(departement: str) -> str:
    """Retourne le préfixe de code postal pour un département (gère 2A, 2B, DOM)."""
    dept = departement.upper().strip()
    if dept in ("2A", "2B"):
        return dept
    try:
        return str(int(dept)).zfill(2)
    except ValueError:
        return dept


def _fhir_url_departement(departement: str, offset: int = 0) -> str:
    prefixe = _prefixe_cp(departement)
    return (
        "https://api.annuaire.sante.fr/fhir/v1/Organization"
        f"?type=SA25"
        f"&address-postalcode={prefixe}*"
        f"&active=true"
        f"&_count=200"
        f"&_offset={offset}"
    )


def _parser_entree_fhir(resource: dict, departement: str) -> Optional[Dict[str, Any]]:
    """Parse une entrée FHIR Organization et retourne un dict pharmacie."""
    nom = _nettoyer_nom(resource.get("name", ""))
    if not nom:
        return None

    adresses = resource.get("address", [])
    adresse_data = adresses[0] if adresses else {}
    lignes = adresse_data.get("line", [])
    adresse = " ".join(lignes).strip() or None
    ville = _nettoyer_nom(adresse_data.get("city", ""))
    cp = adresse_data.get("postalCode", "")

    telecoms = resource.get("telecom", [])
    telephone = next(
        (_nettoyer_tel(t.get("value", "")) for t in telecoms if t.get("system") == "phone"), ""
    )
    email = next(
        (t.get("value", "") for t in telecoms if t.get("system") == "email"), ""
    )

    if not cp:
        return None

    return {
        "nom": nom,
        "adresse": adresse,
        "ville": ville or None,
        "code_postal": cp,
        "departement": departement,
        "telephone": telephone or None,
        "email": email or None,
        "source": "scraping_data_gouv",
    }


def scraper_annuaire_sante(departement: str, callback=None) -> List[Dict[str, Any]]:
    """
    Scrape l'API officielle annuaire santé (FHIR) avec le code SA25 (officines).
    Gère la pagination automatiquement.
    """
    pharmacies = []
    headers = {
        "Accept": "application/fhir+json, application/json",
        "User-Agent": random.choice(USER_AGENTS),
    }

    if callback:
        callback(f"  [API Sante] Departement {departement} — requete en cours...")

    offset = 0
    page = 0
    total_annonce = None

    while True:
        url = _fhir_url_departement(departement, offset)
        resp = _get(url, headers, timeout=30)

        if not resp:
            if callback:
                callback(f"  [API Sante] Indisponible (pas de connexion ou timeout)")
            break

        try:
            data = resp.json()
        except Exception:
            if callback:
                callback(f"  [API Sante] Reponse invalide")
            break

        if total_annonce is None:
            total_annonce = data.get("total", 0)
            if callback:
                callback(f"  [API Sante] {total_annonce} pharmacies trouvees dans le departement {departement}")

        entrees = data.get("entry", [])
        if not entrees:
            break

        for entree in entrees:
            resource = entree.get("resource", {})
            pharm = _parser_entree_fhir(resource, departement)
            if pharm:
                pharmacies.append(pharm)

        # Vérifier s'il y a une page suivante via les liens FHIR
        liens = data.get("link", [])
        url_next = next((l.get("url") for l in liens if l.get("relation") == "next"), None)

        if url_next:
            offset += len(entrees)
            page += 1
            if page > 20:  # Sécurité max 4000 résultats
                break
            time.sleep(0.3)
        else:
            break

    if callback:
        callback(f"  [API Sante] {len(pharmacies)} pharmacies recuperees")

    return pharmacies


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 2 : Overpass API (OpenStreetMap) — couverture complémentaire
# ─────────────────────────────────────────────────────────────────────────────

def scraper_overpass(departement: str, callback=None) -> List[Dict[str, Any]]:
    """
    Scrape les pharmacies via OpenStreetMap (Overpass API).
    Fiable, rapide, couvre ~70% des officines françaises.
    """
    prefixe = _prefixe_cp(departement)

    query = (
        f'[out:json][timeout:60];'
        f'('
        f'node[amenity=pharmacy]["addr:postcode"~"^{prefixe}"];'
        f'way[amenity=pharmacy]["addr:postcode"~"^{prefixe}"];'
        f');'
        f'out center;'
    )

    if callback:
        callback(f"  [OpenStreetMap] Departement {departement} — requete en cours...")

    resp = _post("https://overpass-api.de/api/interpreter", {"data": query}, timeout=90)
    if not resp:
        if callback:
            callback(f"  [OpenStreetMap] Indisponible")
        return []

    pharmacies = []
    try:
        data = resp.json()
        elements = data.get("elements", [])

        if callback:
            callback(f"  [OpenStreetMap] {len(elements)} pharmacies trouvees")

        for el in elements:
            tags = el.get("tags", {})
            nom = _nettoyer_nom(tags.get("name", tags.get("operator", "")))
            if not nom:
                continue

            cp = tags.get("addr:postcode") or ""
            if not cp or not cp.startswith(prefixe):
                continue

            ville = _nettoyer_nom(
                tags.get("addr:city") or tags.get("addr:municipality") or tags.get("addr:town") or ""
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

    except Exception as e:
        logger.error(f"Erreur Overpass département {departement} : {e}")
        if callback:
            callback(f"  [OpenStreetMap] Erreur parsing : {e}")

    return pharmacies


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE 3 : Pages Jaunes — enrichissement téléphone/email
# ─────────────────────────────────────────────────────────────────────────────

def scraper_pages_jaunes_ville(ville: str, code_postal: str) -> List[Dict[str, Any]]:
    """Scrape Pages Jaunes pour enrichir une ville avec emails/téléphones."""
    ville_url = ville.lower().replace(" ", "-").replace("'", "-")
    url = (
        f"https://www.pagesjaunes.fr/annuaire/chercherlespros"
        f"?quoiqui=pharmacie&ou={ville_url}-{code_postal}"
    )

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Referer": "https://www.pagesjaunes.fr/",
    }

    pharmacies = []
    resp = _get(url, headers, timeout=20)
    if not resp:
        return pharmacies

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        fiches = (
            soup.select("article.bi-generic")
            or soup.select("li.bi-item")
            or soup.select("[data-bi-id]")
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

            email_el = fiche.select_one("a[href^='mailto:']")
            email = ""
            if email_el:
                email = email_el.get("href", "").replace("mailto:", "").strip()

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
# FUSION ET DÉDOUBLONNAGE
# ─────────────────────────────────────────────────────────────────────────────

def _fusionner(base: Dict, complement: Dict) -> Dict:
    """Fusionne deux fiches pharmacie — complète les champs vides."""
    result = dict(base)
    for cle in ("adresse", "ville", "telephone", "email"):
        if not result.get(cle) and complement.get(cle):
            result[cle] = complement[cle]
    return result


def _dedoublonner(pharmacies: List[Dict]) -> List[Dict]:
    """
    Dédoublonne par (nom normalisé + code postal).
    Fusionne les infos complémentaires entre doublons.
    """
    index: Dict[tuple, Dict] = {}
    for pharm in pharmacies:
        nom_norm = pharm.get("nom", "").lower().strip()
        cp = str(pharm.get("code_postal", "")).strip()
        if not nom_norm or not cp:
            continue
        cle = (nom_norm, cp)
        if cle in index:
            index[cle] = _fusionner(index[cle], pharm)
        else:
            index[cle] = pharm
    return list(index.values())


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
    Scrape toutes les pharmacies d'un département depuis toutes les sources.
    Retourne les compteurs : inserees / doublons / erreurs.
    """
    compteurs = {"inserees": 0, "doublons": 0, "erreurs": 0}

    def log(msg: str):
        logger.info(msg)
        if callback:
            callback(msg)

    def arrete() -> bool:
        return bool(stop_flag and stop_flag[0])

    log(f"========================================")
    log(f"Scraping departement {departement}")
    log(f"========================================")

    toutes_pharmacies: List[Dict] = []

    # ── Source 1 : API Annuaire Santé ──────────────────────────────────────
    if not arrete():
        try:
            pharmacies_sante = scraper_annuaire_sante(departement, callback=log)
            toutes_pharmacies.extend(pharmacies_sante)
        except Exception as e:
            log(f"  [API Sante] Erreur : {e}")

    # ── Source 2 : OpenStreetMap / Overpass ─────────────────────────────────
    if not arrete():
        time.sleep(1)
        try:
            pharmacies_osm = scraper_overpass(departement, callback=log)
            toutes_pharmacies.extend(pharmacies_osm)
        except Exception as e:
            log(f"  [OpenStreetMap] Erreur : {e}")

    log(f"Total brut (avant dedoublonnage) : {len(toutes_pharmacies)}")

    # ── Dédoublonnage inter-sources ──────────────────────────────────────────
    uniques = _dedoublonner(toutes_pharmacies)
    log(f"Total apres dedoublonnage : {len(uniques)} pharmacies uniques")

    if not uniques:
        log(f"Aucune pharmacie trouvee dans le departement {departement}.")
        log(f"Verifiez votre connexion Internet.")
        return compteurs

    # ── Source 3 : Enrichissement Pages Jaunes sur les villes trouvées ──────
    if not arrete():
        villes_uniques = {}
        for p in uniques:
            v = p.get("ville", "")
            cp = p.get("code_postal", "")
            if v and cp and v not in villes_uniques:
                villes_uniques[v] = cp

        nb_villes = len(villes_uniques)
        log(f"  [Pages Jaunes] Enrichissement sur {nb_villes} villes...")

        enrichissements_pj = []
        for i, (ville, cp) in enumerate(list(villes_uniques.items())[:20]):  # Max 20 villes
            if arrete():
                break
            log(f"  [Pages Jaunes] {ville} ({i+1}/{min(nb_villes, 20)})...")
            pj = scraper_pages_jaunes_ville(ville, cp)
            enrichissements_pj.extend(pj)
            time.sleep(random.uniform(1.5, 2.5))

        # Fusionner les enrichissements PJ dans les fiches existantes
        if enrichissements_pj:
            index_pj: Dict[tuple, Dict] = {}
            for p in enrichissements_pj:
                cle = (p.get("nom", "").lower().strip(), str(p.get("code_postal", "")))
                if cle[0]:
                    index_pj[cle] = p

            for i, pharm in enumerate(uniques):
                cle = (pharm.get("nom", "").lower().strip(), str(pharm.get("code_postal", "")))
                if cle in index_pj:
                    uniques[i] = _fusionner(pharm, index_pj[cle])

            log(f"  [Pages Jaunes] {len(enrichissements_pj)} fiches PJ traitees")

    # ── Insertion en base de données ─────────────────────────────────────────
    log(f"Insertion de {len(uniques)} pharmacies en base...")

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
                result = inserer_pharmacie(db_path, pharm)
                if result:
                    compteurs["inserees"] += 1
                else:
                    compteurs["doublons"] += 1
        except Exception as e:
            compteurs["erreurs"] += 1
            logger.error(f"Erreur insertion {pharm.get('nom')} : {e}")

    log(f"========================================")
    log(
        f"TERMINE — {compteurs['inserees']} inserees | "
        f"{compteurs['doublons']} doublons | "
        f"{compteurs['erreurs']} erreurs"
    )
    log(f"========================================")

    return compteurs
