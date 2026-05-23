"""
Module Pappers — Récupération du chiffre d'affaires via Pappers.fr.
Utilise BeautifulSoup uniquement (Pappers affiche les données en HTML).
Tout est dans des try/except : ne jamais planter.
"""

import sys
import os
import re
import time
import random
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    BASE_DIR, creer_logger, sauvegarder_progression,
    DELAI_PAPPERS_MIN, DELAI_PAPPERS_MAX, TIMEOUT_HTTP,
)
from modules.modeles import Parapharmacie

logger = creer_logger("pappers")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.google.fr/",
}

# Seuils de détection de blocage
SEUIL_PAUSE = 3    # nb d'échecs avant pause 60s
SEUIL_ABANDON = 5  # nb d'échecs avant abandon total


def extraire_ca_depuis_html(html: str) -> Tuple[str, str]:
    """
    Extrait le chiffre d'affaires et l'année depuis une page Pappers.
    Retourne (chiffre_affaires, annee) ou ("", "") si non trouvé.
    """
    try:
        soup = BeautifulSoup(html, "lxml")

        # Méthode 1 : balises avec texte "Chiffre d'affaires" en proximité
        for elem in soup.find_all(string=re.compile(r"Chiffre.{0,5}affaires", re.IGNORECASE)):
            conteneur = elem.find_parent()
            if not conteneur:
                continue
            # Remonter jusqu'à trouver le montant dans le bloc parent
            for ancetre in [conteneur] + list(conteneur.parents)[:3]:
                texte = ancetre.get_text(" ", strip=True)
                montant = re.search(r'([\d][\d\s ]{2,})\s*€', texte)
                if montant:
                    ca = re.sub(r'[\s ]', '', montant.group(1))
                    annee = re.search(r'20\d{2}', texte)
                    if ca.isdigit() and int(ca) > 1000:
                        return ca, (annee.group(0) if annee else "")

        # Méthode 2 : classes CSS contenant "finance", "ca", "chiffre"
        for elem in soup.find_all(
            ["div", "td", "span", "p"],
            class_=re.compile(r'(finance|chiffre|ca|bilan|revenue)', re.IGNORECASE)
        ):
            texte = elem.get_text(" ", strip=True)
            montant = re.search(r'([\d][\d\s ]{2,})\s*€', texte)
            if montant:
                ca = re.sub(r'[\s ]', '', montant.group(1))
                annee = re.search(r'20\d{2}', texte)
                if ca.isdigit() and int(ca) > 1000:
                    return ca, (annee.group(0) if annee else "")

        # Méthode 3 : chercher un pattern de montant dans tout le texte
        texte_complet = soup.get_text(" ", strip=True)
        # Pattern : montant suivi de "€" ou "euros" à proximité de "CA" ou "chiffre"
        sections = re.split(r'\n{2,}', texte_complet)
        for section in sections:
            if re.search(r'chiffre|affaires|ca\b', section, re.IGNORECASE):
                montants = re.findall(r'(\d[\d\s ]{2,})\s*€', section)
                annees = re.findall(r'20\d{2}', section)
                valides = []
                for m in montants:
                    m_clean = re.sub(r'[\s ]', '', m)
                    if m_clean.isdigit() and int(m_clean) > 5000:
                        valides.append((int(m_clean), m_clean))
                if valides:
                    valides.sort(key=lambda x: x[0], reverse=True)
                    ca = valides[0][1]
                    annee = annees[-1] if annees else ""
                    return ca, annee

        logger.info("[PAPPERS] Structure HTML modifiée - mise à jour nécessaire")
        return "", ""

    except Exception as e:
        logger.error(f"Erreur parsing HTML Pappers : {e}")
        return "", ""


def _pause_aleatoire() -> None:
    """Pause aléatoire avant chaque requête Pappers."""
    time.sleep(random.uniform(DELAI_PAPPERS_MIN, DELAI_PAPPERS_MAX))


def recuperer_ca_par_siret(
    session: requests.Session, siret: str
) -> Tuple[str, str]:
    """Récupère le CA directement depuis la page SIRET Pappers."""
    try:
        _pause_aleatoire()
        url = f"https://www.pappers.fr/entreprise/{siret}"
        reponse = session.get(url, timeout=TIMEOUT_HTTP, allow_redirects=True)

        if reponse.status_code == 404:
            return "", ""
        if reponse.status_code in (429, 503):
            logger.warning(f"Pappers bloqué (status {reponse.status_code}) pour SIRET {siret}")
            return "", ""

        reponse.raise_for_status()
        return extraire_ca_depuis_html(reponse.text)

    except requests.Timeout:
        logger.warning(f"Timeout Pappers SIRET {siret}")
        return "", ""
    except requests.RequestException as e:
        logger.warning(f"Erreur Pappers SIRET {siret} : {e}")
        return "", ""
    except Exception as e:
        logger.error(f"Erreur inattendue Pappers SIRET {siret} : {e}")
        return "", ""


def recuperer_ca_par_nom(
    session: requests.Session, nom: str, code_postal: str
) -> Tuple[str, str]:
    """Recherche le CA via Pappers en cherchant par nom + code postal."""
    try:
        _pause_aleatoire()
        terme = f"{nom} {code_postal}".strip()
        url = f"https://www.pappers.fr/recherche?q={requests.utils.quote(terme)}"

        reponse = session.get(url, timeout=TIMEOUT_HTTP, allow_redirects=True)
        if reponse.status_code in (429, 503):
            return "", ""
        reponse.raise_for_status()

        soup = BeautifulSoup(reponse.text, "lxml")
        lien = soup.find("a", href=re.compile(r"/entreprise/"))

        if not lien:
            return "", ""

        _pause_aleatoire()
        url_entreprise = "https://www.pappers.fr" + lien["href"]
        reponse2 = session.get(url_entreprise, timeout=TIMEOUT_HTTP, allow_redirects=True)
        if reponse2.status_code in (429, 503):
            return "", ""
        reponse2.raise_for_status()
        return extraire_ca_depuis_html(reponse2.text)

    except requests.Timeout:
        logger.warning(f"Timeout Pappers nom='{nom}'")
        return "", ""
    except (requests.RequestException, KeyError, AttributeError) as e:
        logger.warning(f"Erreur Pappers nom='{nom}' : {e}")
        return "", ""
    except Exception as e:
        logger.error(f"Erreur inattendue Pappers nom='{nom}' : {e}")
        return "", ""


def enrichir(
    parapharmacies: List[Parapharmacie],
    zone: str = "",
) -> List[Parapharmacie]:
    """
    Enrichit les objets Parapharmacie avec le CA Pappers.
    Résistant aux blocages : pause, puis abandon gracieux.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    total = len(parapharmacies)
    enrichis = 0
    echecs_consecutifs = 0
    abandon = False

    for i, p in enumerate(parapharmacies):
        if abandon:
            p.chiffre_affaires = ""
            p.source_ca = "Pappers indisponible"
            parapharmacies[i] = p
            continue

        print(f"  [Pappers {i+1}/{total}] {p.nom[:45]:<45}", end="\r")

        ca, annee = "", ""

        try:
            if p.siret:
                ca, annee = recuperer_ca_par_siret(session, p.siret)
            elif p.nom and p.code_postal:
                ca, annee = recuperer_ca_par_nom(session, p.nom, p.code_postal)

            if ca:
                p.chiffre_affaires = ca
                p.annee_bilan = annee
                p.source_ca = "Pappers"
                enrichis += 1
                echecs_consecutifs = 0
                logger.info(f"Pappers OK : '{p.nom}' → CA={ca} ({annee})")
            else:
                echecs_consecutifs += 1
                p.source_ca = "Non disponible"
                logger.info(f"Pappers : CA non trouvé pour '{p.nom}'")

                if echecs_consecutifs >= SEUIL_PAUSE:
                    print(f"\n  [PAPPERS] Pause anti-blocage 60s...")
                    logger.warning("Pause anti-blocage Pappers activée")
                    time.sleep(60)
                    echecs_consecutifs = 0

                if echecs_consecutifs >= SEUIL_ABANDON:
                    print(f"\n  [PAPPERS] Trop d'échecs consécutifs, Pappers abandonné")
                    logger.error("Pappers abandonné après trop d'échecs")
                    p.source_ca = "Pappers indisponible"
                    abandon = True

        except Exception as e:
            logger.error(f"Erreur inattendue Pappers '{p.nom}' : {e}")
            p.source_ca = "Erreur"
            echecs_consecutifs += 1

        parapharmacies[i] = p

        # Sauvegarde progressive toutes les 10 entrées
        if (i + 1) % 10 == 0 and zone:
            sauvegarder_progression(parapharmacies, zone, 3)

    print()  # Saut de ligne après la progression

    avec_ca = sum(1 for p in parapharmacies if p.chiffre_affaires)
    logger.info(f"Pappers terminé : {avec_ca}/{total} CA récupérés")

    if zone:
        sauvegarder_progression(parapharmacies, zone, 3)

    return parapharmacies


if __name__ == "__main__":
    import glob
    import json

    print("=" * 55)
    print("  TEST MODULE PAPPERS — Lyon (5 premières entrées)")
    print("=" * 55)

    # Charger les données depuis le cache le plus récent disponible
    for pattern in [
        os.path.join(BASE_DIR, "cache", "progression_lyon_phase2.json"),
        os.path.join(BASE_DIR, "cache", "progression_lyon_phase1.json"),
    ]:
        fichiers = glob.glob(pattern)
        if fichiers:
            break
    else:
        fichiers = glob.glob(os.path.join(BASE_DIR, "cache", "osm_lyon_*.json"))

    if not fichiers:
        print("  [INFO] Pas de cache disponible, lancement OSM...")
        from modules import osm
        donnees = osm.rechercher("Lyon")
    else:
        fichier = sorted(fichiers)[-1]
        print(f"  [INFO] Chargement : {os.path.basename(fichier)}")
        with open(fichier, 'r', encoding='utf-8') as f:
            donnees = [Parapharmacie(**d) for d in json.load(f)]

    print(f"  [INFO] {len(donnees)} parapharmacies (test limité à 5)\n")
    donnees_test = donnees[:5]

    donnees_enrichies = enrichir(donnees_test, "Lyon")

    print(f"\n{'=' * 55}")
    print("  RÉSULTATS PAPPERS :")
    avec_ca = sum(1 for p in donnees_enrichies if p.chiffre_affaires)
    print(f"  CA récupérés : {avec_ca}/{len(donnees_enrichies)}\n")

    for p in donnees_enrichies:
        if p.chiffre_affaires:
            statut = f"CA={p.chiffre_affaires} € ({p.annee_bilan})"
        else:
            statut = f"Non trouvé [{p.source_ca}]"
        print(f"  {p.nom[:42]:<42} → {statut}")

    print(f"{'=' * 55}")
