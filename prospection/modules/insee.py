"""
Module INSEE — Enrichissement légal via l'API Sirene v3.11.
Ajoute SIRET, dirigeant, statut juridique, date de création.
"""

import sys
import os
import json
import time
import base64
from typing import List, Optional

import requests
from rapidfuzz import fuzz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    BASE_DIR, creer_logger, normaliser_nom_fichier, sauvegarder_progression,
    INSEE_API_KEY, DELAI_INSEE, TIMEOUT_HTTP,
    SEUIL_MATCH_AUTO, SEUIL_MATCH_PROBABLE,
    INSEE_MAX_REQUETES_PAR_MINUTE,
)
from modules.modeles import Parapharmacie

logger = creer_logger("insee")

# Nouveau portail INSEE (l'ancienne URL api.insee.fr est dépréciée)
URL_TOKEN = "https://portail-api.insee.fr/token"
URL_SIRET = "https://api.insee.fr/entreprises/sirene/V3.11/siret"

INSTRUCTIONS_CLE = """
┌──────────────────────────────────────────────────────┐
│ ACTIVATION INSEE (gratuit)                           │
│ 1. Aller sur https://portail-api.insee.fr/           │
│ 2. Créer un compte                                   │
│ 3. Créer une application → souscrire à "Sirene"      │
│ 4. Copier Consumer Key ET Consumer Secret            │
│ 5. Coller dans config.py :                           │
│    INSEE_API_KEY = "consumer_key:consumer_secret"    │
└──────────────────────────────────────────────────────┘
"""


class GestionnaireRequetesINSEE:
    """Gère l'authentification OAuth2 et le débit des requêtes INSEE."""

    def __init__(self, api_key: str, api_secret: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret if api_secret else api_key
        self.requetes_cette_minute = 0
        self.debut_minute = time.time()
        self.token: Optional[str] = None
        self.token_expiration: float = 0

    def _obtenir_nouveau_token(self) -> Optional[str]:
        """Obtient un token OAuth2 depuis l'API INSEE."""
        try:
            credentials = base64.b64encode(
                f"{self.api_key}:{self.api_secret}".encode()
            ).decode()

            reponse = requests.post(
                URL_TOKEN,
                data={"grant_type": "client_credentials"},
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=TIMEOUT_HTTP,
            )
            reponse.raise_for_status()
            data = reponse.json()

            self.token_expiration = time.time() + data.get("expires_in", 3600) - 60
            token = data.get("access_token")
            logger.info("Token INSEE obtenu avec succès")
            return token

        except requests.HTTPError as e:
            logger.error(f"Erreur HTTP token INSEE : {e} — {e.response.text[:200]}")
            print(f"  [INSEE] Erreur d'authentification : {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"Erreur réseau token INSEE : {e}")
            print(f"  [INSEE] Erreur réseau lors de l'authentification : {e}")
            return None

    def renouveler_token_si_necessaire(self) -> bool:
        """Renouvelle le token s'il a expiré."""
        if time.time() >= self.token_expiration or self.token is None:
            self.token = self._obtenir_nouveau_token()
        return self.token is not None

    def attendre_si_necessaire(self) -> None:
        """Respecte la limite de 28 requêtes/minute de l'API INSEE."""
        if time.time() - self.debut_minute > 60:
            self.requetes_cette_minute = 0
            self.debut_minute = time.time()

        if self.requetes_cette_minute >= INSEE_MAX_REQUETES_PAR_MINUTE:
            attente = 60 - (time.time() - self.debut_minute)
            print(f"\n  [INSEE] Pause {attente:.0f}s (limite de débit atteinte)...")
            time.sleep(max(attente, 0) + 1)
            self.requetes_cette_minute = 0
            self.debut_minute = time.time()

        self.requetes_cette_minute += 1
        time.sleep(DELAI_INSEE)

    def rechercher_etablissement(
        self, nom: str, code_postal: str
    ) -> Optional[dict]:
        """Cherche un établissement dans la base Sirene par nom et code postal."""
        if not self.renouveler_token_si_necessaire():
            return None

        self.attendre_si_necessaire()

        try:
            # Nettoyer le nom pour la requête Lucene
            nom_clean = nom.replace('"', ' ').replace("'", ' ').strip()

            params = {
                "q": (
                    f'denominationUniteLegale:"{nom_clean}" '
                    f'AND codePostalEtablissement:"{code_postal}"'
                ),
                "nombre": 5,
            }

            reponse = requests.get(
                URL_SIRET,
                params=params,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                },
                timeout=TIMEOUT_HTTP,
            )

            if reponse.status_code == 404:
                return None
            if reponse.status_code == 401:
                # Token expiré : forcer le renouvellement
                self.token_expiration = 0
                return None
            if reponse.status_code == 429:
                logger.warning("Limite INSEE atteinte (429), pause 60s")
                time.sleep(60)
                return None

            reponse.raise_for_status()
            data = reponse.json()
            etablissements = data.get("etablissements", [])
            return etablissements[0] if etablissements else None

        except requests.Timeout:
            logger.error(f"Timeout INSEE pour '{nom}'")
            return None
        except requests.RequestException as e:
            logger.error(f"Erreur INSEE pour '{nom}' : {e}")
            return None


def extraire_dirigeant(unite_legale: dict) -> str:
    """Extrait le nom du dirigeant depuis les périodes de l'unité légale."""
    periodes = unite_legale.get("periodesUniteLegale", [])
    if periodes:
        periode = periodes[0]
        prenom = periode.get("prenom1UniteLegale") or ""
        nom = periode.get("nomUniteLegale") or ""
        if prenom or nom:
            return f"{prenom} {nom}".strip()

    # Fallback direct sur l'unité légale
    prenom = unite_legale.get("prenom1UniteLegale") or ""
    nom = unite_legale.get("nomUniteLegale") or ""
    return f"{prenom} {nom}".strip()


def enrichir_depuis_etablissement(
    p: Parapharmacie, etablissement: dict
) -> Parapharmacie:
    """Applique les données d'un établissement INSEE à un objet Parapharmacie."""
    unite_legale = etablissement.get("uniteLegale", {})

    nom_legal = (
        unite_legale.get("denominationUniteLegale") or
        unite_legale.get("nomUniteLegale") or ""
    )

    # Scoring RapidFuzz pour valider la correspondance
    score = fuzz.ratio(
        p.nom.lower().strip(),
        nom_legal.lower().strip()
    )

    if score >= SEUIL_MATCH_AUTO:
        p.siret = etablissement.get("siret", "")
        p.nom_legal = nom_legal
        p.dirigeant = extraire_dirigeant(unite_legale)
        p.statut_juridique = unite_legale.get("categorieJuridiqueUniteLegale", "")
        p.date_creation = unite_legale.get("dateCreationUniteLegale", "")
        p.etat_administratif = etablissement.get("etatAdministratifEtablissement", "")
        p.confiance_match = score
        p.statut_match = "AUTO"
    elif score >= SEUIL_MATCH_PROBABLE:
        p.siret = etablissement.get("siret", "")
        p.nom_legal = nom_legal
        p.dirigeant = extraire_dirigeant(unite_legale)
        p.statut_juridique = unite_legale.get("categorieJuridiqueUniteLegale", "")
        p.date_creation = unite_legale.get("dateCreationUniteLegale", "")
        p.etat_administratif = etablissement.get("etatAdministratifEtablissement", "")
        p.confiance_match = score
        p.statut_match = "A_VERIFIER"
    else:
        p.siret = ""
        p.confiance_match = 0
        p.statut_match = "NON_TROUVE"
        logger.info(f"Matching insuffisant pour '{p.nom}' vs '{nom_legal}' : score={score}")

    return p


def enrichir(
    parapharmacies: List[Parapharmacie],
    zone: str = "",
) -> List[Parapharmacie]:
    """
    Enrichit une liste de Parapharmacies avec les données INSEE Sirene.
    Si la clé API est absente, affiche les instructions et passe la phase.
    """
    if not INSEE_API_KEY:
        print(INSTRUCTIONS_CLE)
        print("  [INSEE] Phase ignorée : INSEE_API_KEY non configurée dans config.py")
        logger.warning("INSEE ignoré : clé API absente")
        for p in parapharmacies:
            if not p.statut_match:
                p.statut_match = "INSEE_NON_CONFIGURE"
        return parapharmacies

    # Supporter le format "key:secret" ou juste "key"
    if ":" in INSEE_API_KEY:
        api_key, api_secret = INSEE_API_KEY.split(":", 1)
    else:
        api_key = api_secret = INSEE_API_KEY

    gestionnaire = GestionnaireRequetesINSEE(api_key, api_secret)

    if not gestionnaire.renouveler_token_si_necessaire():
        print("  [INSEE] Authentification échouée, phase ignorée")
        return parapharmacies

    total = len(parapharmacies)
    enrichis = 0

    for i, p in enumerate(parapharmacies):
        print(f"  [INSEE {i+1}/{total}] {p.nom[:45]:<45}", end="\r")
        logger.debug(f"INSEE recherche : '{p.nom}' ({p.code_postal})")

        if not p.nom:
            p.statut_match = "NON_TROUVE"
            continue

        if not p.code_postal:
            logger.info(f"Pas de code postal pour '{p.nom}', skip INSEE")
            p.statut_match = "NON_TROUVE"
            continue

        etablissement = gestionnaire.rechercher_etablissement(p.nom, p.code_postal)

        if etablissement:
            p = enrichir_depuis_etablissement(p, etablissement)
            parapharmacies[i] = p
            if p.siret:
                enrichis += 1
                logger.info(
                    f"INSEE OK : '{p.nom}' → SIRET={p.siret} "
                    f"(score={p.confiance_match}, statut={p.statut_match})"
                )
        else:
            p.confiance_match = 0
            p.statut_match = "NON_TROUVE"
            parapharmacies[i] = p

        # Sauvegarde progressive toutes les 10 entrées
        if (i + 1) % 10 == 0 and zone:
            sauvegarder_progression(parapharmacies, zone, 2)

    print()  # Saut de ligne après la progression

    # Statistiques finales
    auto = sum(1 for p in parapharmacies if p.statut_match == "AUTO")
    a_verifier = sum(1 for p in parapharmacies if p.statut_match == "A_VERIFIER")
    non_trouves = sum(1 for p in parapharmacies if p.statut_match == "NON_TROUVE")

    logger.info(
        f"INSEE terminé : AUTO={auto}, A_VERIFIER={a_verifier}, "
        f"NON_TROUVE={non_trouves}, total={total}"
    )

    if zone:
        sauvegarder_progression(parapharmacies, zone, 2)

    return parapharmacies


if __name__ == "__main__":
    import glob

    print("=" * 55)
    print("  TEST MODULE INSEE — Lyon")
    print("=" * 55)

    # Charger les données OSM depuis le cache
    fichiers_cache = glob.glob(
        os.path.join(BASE_DIR, "cache", "osm_lyon_*.json")
    )

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
    non_config = sum(1 for p in donnees_enrichies if p.statut_match == "INSEE_NON_CONFIGURE")

    print(f"  Total                : {total}")
    print(f"  Avec SIRET           : {avec_siret} ({avec_siret/total*100:.1f}%)" if total else "  Avec SIRET : 0")
    print(f"  Match AUTO           : {auto}")
    print(f"  À vérifier           : {a_verifier}")
    print(f"  Non trouvé           : {non_trouve}")
    if non_config:
        print(f"  INSEE non configuré  : {non_config}")
    print(f"{'=' * 55}")
