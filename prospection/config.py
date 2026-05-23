"""
Configuration centrale de l'application de prospection.
Tous les réglages, constantes, utilitaires partagés.
"""

import sys
import os
import unicodedata
import re
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional

# Vérification version Python
if sys.version_info < (3, 8):
    print("ERREUR : Python 3.8 ou supérieur requis.")
    print(f"Version actuelle : {sys.version}")
    sys.exit(1)

# Dossier racine de l'application (là où se trouve ce fichier)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Clé API INSEE (obtenir gratuitement sur api.insee.fr)
# Format accepté : "consumer_key:consumer_secret" ou juste "consumer_key"
INSEE_API_KEY = ""

# Durée de validité du cache en jours
CACHE_DUREE_JOURS = 7

# Délais entre requêtes (secondes)
DELAI_OSM = 1
DELAI_INSEE = 1
DELAI_PAPPERS_MIN = 2
DELAI_PAPPERS_MAX = 5
DELAI_EMAIL = 2

# Seuils de confiance matching (%)
SEUIL_MATCH_AUTO = 80
SEUIL_MATCH_PROBABLE = 60

# Timeouts HTTP (secondes)
TIMEOUT_HTTP = 10
TIMEOUT_EMAIL = 5

# Limite requêtes INSEE par minute (max officiel : 30)
INSEE_MAX_REQUETES_PAR_MINUTE = 28

# Création des dossiers nécessaires (chemins absolus pour robustesse)
for _dossier in ["cache", "exports", "logs"]:
    os.makedirs(os.path.join(BASE_DIR, _dossier), exist_ok=True)


def creer_logger(nom: str) -> logging.Logger:
    """Crée un logger rotatif dans le dossier logs/."""
    logger = logging.getLogger(nom)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    chemin_log = os.path.join(
        BASE_DIR, "logs",
        f"{nom}_{datetime.now().strftime('%Y%m%d')}.log"
    )
    handler = RotatingFileHandler(
        chemin_log,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    return logger


def normaliser_nom_fichier(nom: str) -> str:
    """Normalise un nom pour l'utiliser dans un nom de fichier."""
    nom = unicodedata.normalize('NFD', nom)
    nom = ''.join(c for c in nom if unicodedata.category(c) != 'Mn')
    nom = re.sub(r'[^a-zA-Z0-9_-]', '_', nom)
    return nom.lower().strip('_')


def normaliser_telephone(tel: str) -> str:
    """Normalise un numéro de téléphone au format XX XX XX XX XX."""
    if not tel:
        return ""
    # Supprimer tout sauf les chiffres et le +
    tel = re.sub(r'[^\d+]', '', tel)
    # Convertir +33 en 0
    if tel.startswith('+33'):
        tel = '0' + tel[3:]
    # Formater en XX XX XX XX XX
    if len(tel) == 10:
        return ' '.join([tel[i:i + 2] for i in range(0, 10, 2)])
    return tel


def sauvegarder_progression(donnees: list, zone: str, phase: int) -> None:
    """Sauvegarde l'état courant pour reprendre en cas de crash."""
    chemin = os.path.join(
        BASE_DIR, "cache",
        f"progression_{normaliser_nom_fichier(zone)}_phase{phase}.json"
    )
    try:
        with open(chemin, 'w', encoding='utf-8') as f:
            json.dump(
                [d.to_dict() if hasattr(d, 'to_dict') else d for d in donnees],
                f, ensure_ascii=False, indent=2
            )
    except Exception as e:
        print(f"[ATTENTION] Impossible de sauvegarder la progression : {e}")


def charger_cache(chemin: str) -> Optional[dict]:
    """Charge un fichier cache JSON avec validation et gestion de corruption."""
    try:
        if not os.path.exists(chemin):
            return None
        with open(chemin, 'r', encoding='utf-8') as f:
            contenu = f.read()
            if not contenu.strip():
                return None
            return json.loads(contenu)
    except json.JSONDecodeError:
        print(f"[ATTENTION] Cache corrompu ignoré : {chemin}")
        os.rename(chemin, chemin + ".corrompu")
        return None
    except Exception as e:
        print(f"[ATTENTION] Erreur lecture cache {chemin} : {e}")
        return None
