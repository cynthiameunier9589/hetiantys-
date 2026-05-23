"""
Module INSEE — Enrichissement légal via l'API Sirene v3.11.
Ajoute SIRET, dirigeant, statut juridique, date de création.

Utilise l'API Sirene "Accès public" du nouveau portail INSEE.
Aucune clé API requise pour l'accès public.
Si INSEE_API_KEY est renseignée dans config.py, une authentification
OAuth2 est tentée pour un quota plus élevé.
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
    BASE_DIR, creer_logger, sauvegarder_progression,
    INSEE_API_KEY, DELAI_INSEE, TIMEOUT_HTTP,
    SEUIL_MATCH_AUTO, SEUIL_MATCH_PROBABLE,
    INSEE_MAX_REQUETES_PAR_MINUTE,
)
from modules.modeles import Parapharmacie

logger = creer_logger("insee")

# Nouvelle URL du portail INSEE (visible sur le Catalogue : api-sirene/3.11)
URL_TOKEN = "https://portail-api.insee.fr/token"
URL_SIRET = "https://api.insee.fr/api-sirene/3.11/siret"
# Ancienne URL conservée en fallback
URL_SIRET_ANCIEN = "https://api.insee.fr/entreprises/sirene/V3.11/siret"


class GestionnaireRequetesINSEE:
    """Gère le débit des requêtes et l'authentification optionnelle INSEE."""

    def __init__(self):
        self.requetes_cette_minute = 0
        self.debut_minute = time.time()
        self.token: Optional[str] = None
        self.token_expiration: float = 0
        self.url_active = URL_SIRET  # bascule sur l'ancien si le nouveau échoue

    def _obtenir_token_oauth2(self, api_key: str, api_secret: str) -> Optional[str]:
        """Tente d'obtenir un token OAuth2 (optionnel, pour quota augmenté)."""
        try:
            credentials = base64.b64encode(
                f"{api_key}:{api_secret}".encode()
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
            logger.info("Token INSEE obtenu avec succès")
            return data.get("access_token")
        except Exception as e:
            logger.warning(f"Token INSEE optionnel non obtenu : {e}")
            return None

    def preparer(self) -> None:
        """Initialise l'authentification si une clé est configurée."""
        if INSEE_API_KEY:
            if ":" in INSEE_API_KEY:
                key, secret = INSEE_API_KEY.split(":", 1)
            else:
                key = secret = INSEE_API_KEY
            self.token = self._obtenir_token_oauth2(key, secret)
            if self.token:
                print("  [INSEE] Authentification OAuth2 active")
            else:
                print("  [INSEE] Mode accès public (sans token)")
        else:
            print("  [INSEE] Mode accès public (sans clé API)")

    def attendre_si_necessaire(self) -> None:
        """Respecte la limite de débit INSEE."""
        if time.time() - self.debut_minute > 60:
            self.requetes_cette_minute = 0
            self.debut_minute = time.time()

        if self.requetes_cette_minute >= INSEE_MAX_REQUETES_PAR_MINUTE:
            attente = 60 - (time.time() - self.debut_minute)
            print(f"\n  [INSEE] Pause {attente:.0f}s (limite de débit)...")
            time.sleep(max(attente, 0) + 1)
            self.requetes_cette_minute = 0
            self.debut_minute = time.time()

        self.requetes_cette_minute += 1
        time.sleep(DELAI_INSEE)

    def _construire_headers(self) -> dict:
        """Construit les headers HTTP avec ou sans token."""
        headers = {"Accept": "application/json"}
        if self.token and time.time() < self.token_expiration:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def rechercher_etablissement(self, nom: str, code_postal: str) -> Optional[dict]:
        """Cherche un établissement Sirene par nom et code postal."""
        self.attendre_si_necessaire()

        nom_clean = nom.replace('"', ' ').replace("'", ' ').strip()
        params = {
            "q": (
                f'denominationUniteLegale:"{nom_clean}" '
                f'AND codePostalEtablissement:"{code_postal}"'
            ),
            "nombre": 5,
        }
        headers = self._construire_headers()

        # Essayer la nouvelle URL, puis l'ancienne en fallback
        for url in [self.url_active, URL_SIRET_ANCIEN]:
            try:
                reponse = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_HTTP)

                if reponse.status_code == 404:
                    return None
                if reponse.status_code == 429:
                    logger.warning("Limite INSEE (429), pause 60s")
                    time.sleep(60)
                    return None
                if reponse.status_code in (301, 302, 410):
                    # URL redirigée : basculer sur l'autre URL
                    self.url_active = URL_SIRET_ANCIEN if url == URL_SIRET else URL_SIRET
                    continue

                reponse.raise_for_status()
                data = reponse.json()

                # Adapter selon la structure de réponse (ancienne ou nouvelle API)
                etablissements = (
                    data.get("etablissements") or
                    data.get("data") or
                    []
                )
                # Nouvelle API : les données peuvent être sous une clé différente
                if not etablissements and isinstance(data, dict):
                    for cle in data:
                        if isinstance(data[cle], list) and data[cle]:
                            etablissements = data[cle]
                            break

                return etablissements[0] if etablissements else None

            except requests.Timeout:
                logger.warning(f"Timeout INSEE ({url}) pour '{nom}'")
                continue
            except requests.RequestException as e:
                logger.warning(f"Erreur INSEE ({url}) pour '{nom}' : {e}")
                continue

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

    prenom = unite_legale.get("prenom1UniteLegale") or ""
    nom = unite_legale.get("nomUniteLegale") or ""
    return f"{prenom} {nom}".strip()


def enrichir_depuis_etablissement(p: Parapharmacie, etablissement: dict) -> Parapharmacie:
    """Applique les données d'un établissement INSEE à un objet Parapharmacie."""
    unite_legale = etablissement.get("uniteLegale", {})

    nom_legal = (
        unite_legale.get("denominationUniteLegale") or
        unite_legale.get("nomUniteLegale") or ""
    )

    score = fuzz.ratio(p.nom.lower().strip(), nom_legal.lower().strip())

    if score >= SEUIL_MATCH_AUTO:
        statut = "AUTO"
    elif score >= SEUIL_MATCH_PROBABLE:
        statut = "A_VERIFIER"
    else:
        p.siret = ""
        p.confiance_match = 0
        p.statut_match = "NON_TROUVE"
        logger.info(f"Matching insuffisant '{p.nom}' vs '{nom_legal}' : score={score}")
        return p

    p.siret = etablissement.get("siret", "")
    p.nom_legal = nom_legal
    p.dirigeant = extraire_dirigeant(unite_legale)
    p.statut_juridique = unite_legale.get("categorieJuridiqueUniteLegale", "")
    p.date_creation = unite_legale.get("dateCreationUniteLegale", "")
    p.etat_administratif = etablissement.get("etatAdministratifEtablissement", "")
    p.confiance_match = score
    p.statut_match = statut
    return p


def enrichir(parapharmacies: List[Parapharmacie], zone: str = "") -> List[Parapharmacie]:
    """
    Enrichit les Parapharmacies avec les données INSEE Sirene.
    Fonctionne en accès public (sans clé) ou avec OAuth2 si INSEE_API_KEY est définie.
    """
    gestionnaire = GestionnaireRequetesINSEE()
    gestionnaire.preparer()

    total = len(parapharmacies)
    enrichis = 0

    for i, p in enumerate(parapharmacies):
        print(f"  [INSEE {i+1}/{total}] {p.nom[:45]:<45}", end="\r")

        if not p.nom or not p.code_postal:
            p.statut_match = "NON_TROUVE"
            continue

        etablissement = gestionnaire.rechercher_etablissement(p.nom, p.code_postal)

        if etablissement:
            p = enrichir_depuis_etablissement(p, etablissement)
            parapharmacies[i] = p
            if p.siret:
                enrichis += 1
                logger.info(f"INSEE OK : '{p.nom}' → SIRET={p.siret} (score={p.confiance_match})")
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
    print(f"  Avec SIRET  : {avec_siret} ({avec_siret/total*100:.1f}%)" if total else "")
    print(f"  AUTO        : {auto}")
    print(f"  À vérifier  : {a_verifier}")
    print(f"  Non trouvé  : {non_trouve}")

    print(f"\n  Détail :")
    for p in donnees_enrichies:
        siret = p.siret or "—"
        print(f"  {p.nom[:40]:<40} → SIRET={siret} [{p.statut_match}]")
    print(f"{'=' * 55}")
