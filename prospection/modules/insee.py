"""
Module INSEE — Enrichissement légal via l'API Annuaire Entreprises (data.gouv.fr).
Données Sirene officielles : SIRET, dirigeant, statut juridique, date de création.

API gratuite, sans compte et sans clé API.
Source : https://recherche-entreprises.api.gouv.fr
"""

import sys
import os
import json
import time
from typing import List, Optional

import requests
from rapidfuzz import fuzz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    BASE_DIR, creer_logger, sauvegarder_progression,
    DELAI_INSEE, TIMEOUT_HTTP,
    SEUIL_MATCH_AUTO, SEUIL_MATCH_PROBABLE,
)
from modules.modeles import Parapharmacie

logger = creer_logger("insee")

# API officielle data.gouv.fr — Sirene sans authentification
URL_RECHERCHE = "https://recherche-entreprises.api.gouv.fr/search"


def _attendre() -> None:
    """Pause entre requêtes pour respecter le fair-use de l'API."""
    time.sleep(DELAI_INSEE)


def rechercher_etablissement(nom: str, code_postal: str, ville: str = "") -> Optional[dict]:
    """
    Cherche une entreprise via l'API Annuaire Entreprises.
    Si code_postal absent, cherche par nom + ville. Si ville aussi absente, par nom seul.
    """
    _attendre()
    try:
        nom_clean = nom.replace('"', ' ').replace("'", ' ').strip()

        # Construire la requête selon les données disponibles
        if code_postal:
            params = {"q": nom_clean, "code_postal": code_postal, "per_page": 5}
        elif ville:
            # Inclure la ville dans la requête textuelle
            params = {"q": f"{nom_clean} {ville}", "per_page": 5}
        else:
            params = {"q": nom_clean, "per_page": 5}
        reponse = requests.get(URL_RECHERCHE, params=params, timeout=TIMEOUT_HTTP)

        if reponse.status_code == 404:
            return None
        if reponse.status_code == 429:
            logger.warning("Limite API Annuaire Entreprises (429), pause 30s")
            time.sleep(30)
            return None

        reponse.raise_for_status()
        data = reponse.json()
        resultats = data.get("results", [])
        return resultats if resultats else None

    except requests.Timeout:
        logger.warning(f"Timeout API Annuaire pour '{nom}'")
        return None
    except requests.RequestException as e:
        logger.warning(f"Erreur API Annuaire pour '{nom}' : {e}")
        return None
    except Exception as e:
        logger.error(f"Erreur inattendue pour '{nom}' : {e}")
        return None


def extraire_dirigeant(resultats_bruts: list) -> str:
    """Extrait le nom du premier dirigeant depuis les résultats."""
    for entreprise in resultats_bruts:
        dirigeants = entreprise.get("dirigeants", [])
        if dirigeants:
            d = dirigeants[0]
            if d.get("type_dirigeant") == "personne physique":
                prenom = d.get("prenoms", "").split()[0] if d.get("prenoms") else ""
                nom = d.get("nom", "")
                return f"{prenom} {nom}".strip()
            else:
                return d.get("denomination", "")
    return ""


def choisir_meilleur_match(nom_osm: str, resultats: list) -> Optional[tuple]:
    """
    Choisit le résultat le mieux correspondant via RapidFuzz.
    Retourne (résultat, score) ou None si aucun match acceptable.
    """
    meilleur = None
    meilleur_score = 0

    for res in resultats:
        nom_legal = res.get("nom_complet", "") or res.get("nom_raison_sociale", "")
        if not nom_legal:
            continue
        score = fuzz.ratio(nom_osm.lower().strip(), nom_legal.lower().strip())
        if score > meilleur_score:
            meilleur_score = score
            meilleur = (res, score, nom_legal)

    return meilleur if meilleur and meilleur_score >= SEUIL_MATCH_PROBABLE else None


def enrichir_depuis_resultat(p: Parapharmacie, res: dict, score: int, nom_legal: str) -> Parapharmacie:
    """Applique les données d'un résultat API à un objet Parapharmacie."""
    siege = res.get("siege", {})

    p.siret = siege.get("siret", "")
    p.nom_legal = nom_legal
    p.statut_juridique = res.get("nature_juridique", "") or res.get("categorie_juridique_libelle", "")
    p.date_creation = res.get("date_creation", "")
    p.etat_administratif = "A" if res.get("etat_administratif") == "A" else res.get("etat_administratif", "")
    p.confiance_match = score
    p.statut_match = "AUTO" if score >= SEUIL_MATCH_AUTO else "A_VERIFIER"

    # Dirigeant depuis la liste des résultats
    dirigeants = res.get("dirigeants", [])
    if dirigeants:
        d = dirigeants[0]
        if d.get("type_dirigeant") == "personne physique":
            prenom = d.get("prenoms", "").split()[0] if d.get("prenoms") else ""
            p.dirigeant = f"{prenom} {d.get('nom', '')}".strip()
        else:
            p.dirigeant = d.get("denomination", "")

    return p


def enrichir(parapharmacies: List[Parapharmacie], zone: str = "") -> List[Parapharmacie]:
    """
    Enrichit les Parapharmacies avec les données Sirene via l'API data.gouv.fr.
    Aucune clé API requise.
    """
    print("  [INSEE] API Annuaire Entreprises (data.gouv.fr) — sans clé requise")
    total = len(parapharmacies)
    enrichis = 0

    for i, p in enumerate(parapharmacies):
        print(f"  [INSEE {i+1}/{total}] {p.nom[:45]:<45}", end="\r")

        if not p.nom:
            p.statut_match = "NON_TROUVE"
            continue

        resultats = rechercher_etablissement(p.nom, p.code_postal, p.ville or zone)

        if resultats:
            match = choisir_meilleur_match(p.nom, resultats)
            if match:
                res, score, nom_legal = match
                p = enrichir_depuis_resultat(p, res, score, nom_legal)
                parapharmacies[i] = p
                enrichis += 1
                logger.info(f"INSEE OK : '{p.nom}' → SIRET={p.siret} (score={score})")
            else:
                p.confiance_match = 0
                p.statut_match = "NON_TROUVE"
                parapharmacies[i] = p
        else:
            p.confiance_match = 0
            p.statut_match = "NON_TROUVE"
            parapharmacies[i] = p

        if (i + 1) % 10 == 0 and zone:
            sauvegarder_progression(parapharmacies, zone, 2)

    print()

    auto = sum(1 for p in parapharmacies if p.statut_match == "AUTO")
    a_verifier = sum(1 for p in parapharmacies if p.statut_match == "A_VERIFIER")
    non_trouves = sum(1 for p in parapharmacies if p.statut_match == "NON_TROUVE")
    logger.info(f"INSEE terminé : AUTO={auto}, A_VERIFIER={a_verifier}, NON_TROUVE={non_trouves}")

    if zone:
        sauvegarder_progression(parapharmacies, zone, 2)

    return parapharmacies


if __name__ == "__main__":
    import glob

    print("=" * 55)
    print("  TEST MODULE INSEE — Lyon")
    print("=" * 55)

    fichiers_cache = glob.glob(os.path.join(BASE_DIR, "cache", "osm_lyon_*.json"))

    if not fichiers_cache:
        print("  [INFO] Cache OSM absent, lancement du module OSM...")
        from modules import osm
        donnees = osm.rechercher("Lyon")
    else:
        fichier = sorted(fichiers_cache)[-1]
        print(f"  [INFO] Chargement cache : {os.path.basename(fichier)}")
        with open(fichier, 'r', encoding='utf-8') as f:
            donnees = [Parapharmacie(**d) for d in json.load(f)]

    print(f"  [INFO] {len(donnees)} parapharmacies à enrichir\n")

    donnees_enrichies = enrichir(donnees, "Lyon")

    print(f"\n{'=' * 55}")
    print("  RÉSULTATS INSEE :")
    total = len(donnees_enrichies)
    avec_siret = sum(1 for p in donnees_enrichies if p.siret)
    auto = sum(1 for p in donnees_enrichies if p.statut_match == "AUTO")
    a_verifier = sum(1 for p in donnees_enrichies if p.statut_match == "A_VERIFIER")
    non_trouve = sum(1 for p in donnees_enrichies if p.statut_match == "NON_TROUVE")

    print(f"  Total       : {total}")
    if total:
        print(f"  Avec SIRET  : {avec_siret} ({avec_siret/total*100:.1f}%)")
    print(f"  AUTO        : {auto}")
    print(f"  À vérifier  : {a_verifier}")
    print(f"  Non trouvé  : {non_trouve}")

    print(f"\n  Détail :")
    for p in donnees_enrichies:
        siret = p.siret or "—"
        dirigeant = f" | {p.dirigeant}" if p.dirigeant else ""
        print(f"  {p.nom[:38]:<38} SIRET={siret} [{p.statut_match}]{dirigeant}")
    print(f"{'=' * 55}")
