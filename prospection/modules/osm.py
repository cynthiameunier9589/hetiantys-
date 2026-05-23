"""
Module OSM — Recherche de parapharmacies via OpenStreetMap / Overpass API.
Retourne une liste d'objets Parapharmacie.
"""

import sys
import os
import json
import time
import unicodedata
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import requests
from rapidfuzz import process as fuzz_process

# Chemin vers le dossier parent (prospection/) pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    BASE_DIR, creer_logger, normaliser_nom_fichier, normaliser_telephone,
    charger_cache, DELAI_OSM, TIMEOUT_HTTP, CACHE_DUREE_JOURS
)
from modules.modeles import Parapharmacie

logger = creer_logger("osm")

URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"

# Miroirs Overpass par ordre de priorité (le principal est souvent surchargé)
OVERPASS_MIROIRS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

# User-Agent standard navigateur — requis par Nominatim et Overpass
HEADERS_NAVIGATEUR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Alias pour Nominatim (conservé pour clarté)
HEADERS_NOMINATIM = HEADERS_NAVIGATEUR

# Liste de référence pour les suggestions orthographiques
ZONES_CONNUES = [
    "Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes", "Strasbourg",
    "Montpellier", "Bordeaux", "Lille", "Rennes", "Reims", "Saint-Étienne",
    "Toulon", "Grenoble", "Dijon", "Angers", "Nîmes", "Villeurbanne",
    "Île-de-France", "Auvergne-Rhône-Alpes", "Bretagne", "Normandie",
    "Occitanie", "Nouvelle-Aquitaine", "Grand Est", "Pays de la Loire",
    "Hauts-de-France", "Provence-Alpes-Côte d'Azur", "Centre-Val de Loire",
    "Bourgogne-Franche-Comté", "Corse",
    "Rhône", "Bouches-du-Rhône", "Nord", "Gironde", "Hérault",
    "Seine-Maritime", "Haute-Garonne", "Loire-Atlantique", "Var",
    "Isère", "Bas-Rhin", "Ille-et-Vilaine", "Alpes-Maritimes",
    "Ain", "Saône-et-Loire", "Drôme", "Ardèche", "Haute-Savoie", "Savoie",
    "Marne", "Moselle", "Haut-Rhin", "Calvados", "Finistère",
]


def geocoder_zone(zone: str) -> Optional[Tuple[dict, str]]:
    """
    Convertit un nom de zone en résultat Nominatim + admin_level Overpass.
    Retourne (résultat_nominatim, admin_level) ou None si introuvable.
    """
    try:
        time.sleep(DELAI_OSM)
        params = {
            "q": zone,
            "countrycodes": "fr",
            "format": "json",
            "limit": 5,
            "addressdetails": 1,
        }
        reponse = requests.get(
            URL_NOMINATIM,
            params=params,
            headers=HEADERS_NOMINATIM,
            timeout=TIMEOUT_HTTP,
        )
        reponse.raise_for_status()
        resultats = reponse.json()

        if not resultats:
            logger.warning(f"Nominatim : aucun résultat pour '{zone}'")
            return None

        resultat = resultats[0]
        if len(resultats) > 1:
            alternatives = [r.get("display_name", "") for r in resultats[1:3]]
            logger.info(f"Alternatives Nominatim pour '{zone}': {alternatives}")

        # Déterminer l'admin_level en analysant la hiérarchie d'adresse retournée
        # (plus fiable que type/classe pour les communes françaises)
        adresse = resultat.get("address", {})
        nom = resultat.get("name", zone)
        type_zone = resultat.get("type", "")
        classe = resultat.get("class", "")

        if (
            adresse.get("city") == nom or
            adresse.get("town") == nom or
            adresse.get("village") == nom or
            adresse.get("municipality") == nom or
            type_zone in ("city", "town", "village", "hamlet")
        ):
            admin_level = "8"
        elif (
            adresse.get("county") == nom or
            adresse.get("state_district") == nom or
            type_zone == "county"
        ):
            admin_level = "6"
        elif adresse.get("state") == nom or type_zone in ("state", "region"):
            admin_level = "4"
        elif classe == "place":
            admin_level = "8"
        else:
            # Fallback : utiliser l'importance comme indicateur
            importance = float(resultat.get("importance", 0))
            admin_level = "4" if importance > 0.65 else ("6" if importance > 0.45 else "8")

        logger.info(f"Géocodage '{zone}' → nom={nom}, type={type_zone}, admin_level={admin_level}")
        return resultat, admin_level

    except requests.Timeout:
        logger.error(f"Timeout Nominatim pour '{zone}'")
        print(f"  [ERREUR] Timeout lors de la géolocalisation de '{zone}'")
        return None
    except requests.RequestException as e:
        logger.error(f"Erreur Nominatim pour '{zone}' : {e}")
        print(f"  [ERREUR] Impossible de géolocaliser '{zone}' : {e}")
        return None


def suggerer_zones(zone: str) -> List[str]:
    """Suggère des zones proches si la saisie est incorrecte."""
    resultats = fuzz_process.extract(zone, ZONES_CONNUES, limit=3, score_cutoff=55)
    return [r[0] for r in resultats]


def construire_requete_overpass(nom_zone: str, admin_level: str) -> str:
    """Construit la requête Overpass adaptée au type de zone."""
    timeouts = {"4": 180, "6": 120, "8": 60}
    timeout = timeouts.get(admin_level, 60)

    # Échapper les guillemets dans le nom de zone
    nom_zone_safe = nom_zone.replace('"', '\\"')

    return f"""[out:json][timeout:{timeout}];
area[name="{nom_zone_safe}"][admin_level="{admin_level}"]->.zone;
(
  node["shop"="chemist"](area.zone);
  node["shop"="parapharmacy"](area.zone);
  node["amenity"="pharmacy"]["parapharmacy"="yes"](area.zone);
  way["shop"="chemist"](area.zone);
  way["shop"="parapharmacy"](area.zone);
  relation["shop"="chemist"](area.zone);
);
out body;
>;
out skel qt;"""


def requete_overpass(requete: str) -> Optional[dict]:
    """Envoie une requête Overpass en essayant les miroirs disponibles."""
    for miroir in OVERPASS_MIROIRS:
        try:
            reponse = requests.post(
                miroir,
                data={"data": requete},
                headers=HEADERS_NAVIGATEUR,
                timeout=210,
            )
            if reponse.status_code == 406:
                logger.warning(f"Miroir Overpass 406 : {miroir}")
                continue
            reponse.raise_for_status()
            return reponse.json()
        except requests.Timeout:
            logger.warning(f"Timeout miroir Overpass : {miroir}")
            continue
        except requests.RequestException as e:
            logger.warning(f"Erreur miroir Overpass {miroir} : {e}")
            continue
        except json.JSONDecodeError as e:
            logger.error(f"JSON invalide depuis Overpass ({miroir}) : {e}")
            continue

    print("  [ERREUR] Tous les serveurs Overpass sont inaccessibles")
    return None


def parser_elements(donnees: dict) -> List[Parapharmacie]:
    """Parse les éléments Overpass et retourne des objets Parapharmacie."""
    parapharmacies = []
    elements = donnees.get("elements", [])

    for elem in elements:
        tags = elem.get("tags", {})
        if not tags:
            continue

        # Coordonnées : directes pour les nodes, dans 'center' pour ways/relations
        lat = str(elem.get("lat", ""))
        lon = str(elem.get("lon", ""))
        if not lat and "center" in elem:
            lat = str(elem["center"].get("lat", ""))
            lon = str(elem["center"].get("lon", ""))

        # Ignorer les éléments sans coordonnées valides
        if not lat or not lon or lat == "None" or lon == "None":
            continue

        p = Parapharmacie(
            nom=tags.get("name", ""),
            adresse=(
                tags.get("addr:housenumber", "") + " " +
                tags.get("addr:street", "")
            ).strip(),
            ville=(
                tags.get("addr:city", "") or
                tags.get("addr:town", "") or
                tags.get("addr:village", "")
            ),
            code_postal=tags.get("addr:postcode", ""),
            telephone=normaliser_telephone(
                tags.get("phone", "") or tags.get("contact:phone", "")
            ),
            site_web=(
                tags.get("website", "") or tags.get("contact:website", "")
            ),
            email=(
                tags.get("email", "") or tags.get("contact:email", "")
            ),
            latitude=lat,
            longitude=lon,
            source_principale="OpenStreetMap",
        )

        # Garder uniquement les entrées avec un nom
        if p.nom:
            parapharmacies.append(p)

    return parapharmacies


def _normaliser_cle(texte: str) -> str:
    """Normalise un texte pour la comparaison de déduplication."""
    texte = texte.lower().strip()
    texte = unicodedata.normalize('NFD', texte)
    texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn')
    texte = re.sub(r'\s+', ' ', texte)
    return texte


def _compter_champs(p: Parapharmacie) -> int:
    """Compte les champs non vides d'une Parapharmacie."""
    return sum(1 for v in p.to_dict().values() if v and str(v).strip())


def dedupliquer(parapharmacies: List[Parapharmacie]) -> List[Parapharmacie]:
    """Déduplique en gardant l'entrée la plus complète pour chaque doublon."""
    vus: dict = {}
    for p in parapharmacies:
        cle = _normaliser_cle(p.nom) + "|" + _normaliser_cle(p.adresse)
        if cle not in vus or _compter_champs(p) > _compter_champs(vus[cle]):
            vus[cle] = p

    nb_doublons = len(parapharmacies) - len(vus)
    if nb_doublons > 0:
        logger.info(f"Déduplication : {nb_doublons} doublon(s) supprimé(s)")
        print(f"  → {nb_doublons} doublon(s) supprimé(s)")

    return list(vus.values())


def rechercher(zone: str, force_refresh: bool = False) -> List[Parapharmacie]:
    """
    Recherche toutes les parapharmacies d'une zone géographique.
    Utilise le cache si disponible et valide.
    """
    # Vérification du cache (fichiers des 7 derniers jours)
    if not force_refresh:
        # Chercher le cache le plus récent via glob (O(1) au lieu de O(7))
        pattern = os.path.join(BASE_DIR, "cache", f"osm_{normaliser_nom_fichier(zone)}_*.json")
        fichiers_cache = sorted(
            (f for f in __import__('glob').glob(pattern) if not f.endswith('.corrompu')),
            key=os.path.getmtime,
            reverse=True
        )
        if fichiers_cache:
            age_jours = (datetime.now().timestamp() - os.path.getmtime(fichiers_cache[0])) / 86400
            if age_jours <= CACHE_DUREE_JOURS:
                donnees_cache = charger_cache(fichiers_cache[0])
                if donnees_cache is not None:
                    date_str = os.path.basename(fichiers_cache[0]).split('_')[-1].replace('.json', '')
                    print(f"  [CACHE] Données OSM chargées depuis le {date_str}")
                    logger.info(f"Cache OSM utilisé : {fichiers_cache[0]}")
                    return [Parapharmacie(**d) for d in donnees_cache]

    # Géolocalisation
    print(f"  → Géolocalisation de '{zone}'...")
    resultat_geo = geocoder_zone(zone)

    if resultat_geo is None:
        suggestions = suggerer_zones(zone)
        print(f"  [ERREUR] Zone '{zone}' introuvable sur OpenStreetMap.")
        if suggestions:
            print(f"  Vouliez-vous dire : {', '.join(suggestions)} ?")
        return []

    geo, admin_level = resultat_geo
    nom_zone = geo.get("name", zone)
    print(f"  → Zone identifiée : {nom_zone} (niveau administratif : {admin_level})")

    # Requête Overpass
    print(f"  → Interrogation OpenStreetMap (Overpass)...")
    requete = construire_requete_overpass(nom_zone, admin_level)
    donnees_brutes = requete_overpass(requete)

    if donnees_brutes is None:
        return []

    parapharmacies = parser_elements(donnees_brutes)
    print(f"  → {len(parapharmacies)} entrées brutes récupérées")

    # Fallback automatique vers le département si 0 résultat pour une ville
    if len(parapharmacies) == 0 and admin_level == "8":
        adresse = geo.get("address", {})
        dept = (
            adresse.get("county") or
            adresse.get("state_district") or
            adresse.get("state")
        )
        if dept:
            print(f"  Aucun résultat pour '{nom_zone}', élargissement au département '{dept}'...")
            logger.info(f"Fallback département : '{dept}'")
            time.sleep(DELAI_OSM)
            geo2_result = geocoder_zone(dept)
            if geo2_result:
                geo2, _ = geo2_result
                nom_dept = geo2.get("name", dept)
                requete2 = construire_requete_overpass(nom_dept, "6")
                donnees_brutes2 = requete_overpass(requete2)
                if donnees_brutes2:
                    parapharmacies = parser_elements(donnees_brutes2)
                    parapharmacies = dedupliquer(parapharmacies)
                    print(f"  → {len(parapharmacies)} entrées après élargissement au département")

    if len(parapharmacies) == 0:
        print(f"  [ATTENTION] Aucune parapharmacie trouvée pour '{zone}'")
        logger.warning(f"0 résultats pour '{zone}'")
        return []

    # Déduplication
    parapharmacies = dedupliquer(parapharmacies)

    # Sauvegarde en cache
    nom_cache = os.path.join(
        BASE_DIR, "cache",
        f"osm_{normaliser_nom_fichier(zone)}_{datetime.now().strftime('%Y%m%d')}.json"
    )
    try:
        with open(nom_cache, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in parapharmacies], f, ensure_ascii=False, indent=2)
        logger.info(f"Cache OSM sauvegardé : {nom_cache}")
    except Exception as e:
        logger.error(f"Erreur sauvegarde cache OSM : {e}")

    return parapharmacies


if __name__ == "__main__":
    print("=" * 55)
    print("  TEST MODULE OSM — Lyon")
    print("=" * 55)

    resultats = rechercher("Lyon")

    print(f"\n{'=' * 55}")
    print(f"  RÉSULTATS : {len(resultats)} parapharmacies trouvées")
    print(f"{'=' * 55}")

    for i, p in enumerate(resultats[:10], 1):
        print(f"\n[{i}] {p.nom}")
        print(f"    Adresse   : {p.adresse}, {p.code_postal} {p.ville}")
        print(f"    Téléphone : {p.telephone or '—'}")
        print(f"    Email     : {p.email or '—'}")
        print(f"    Site web  : {p.site_web or '—'}")

    if len(resultats) > 10:
        print(f"\n  ... et {len(resultats) - 10} autre(s).")

    print(f"\n  [OK] Cache créé dans cache/")
