"""
Structure de données commune à tous les modules de prospection.
Aucun module n'invente sa propre structure — tous importent depuis ici.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Parapharmacie:
    # Données de base (OSM)
    nom: str = ""
    adresse: str = ""
    ville: str = ""
    code_postal: str = ""
    telephone: str = ""
    site_web: str = ""
    email: str = ""
    latitude: str = ""
    longitude: str = ""
    source_principale: str = ""

    # Données légales (INSEE)
    siret: str = ""
    nom_legal: str = ""
    dirigeant: str = ""
    statut_juridique: str = ""
    date_creation: str = ""
    etat_administratif: str = ""

    # Données financières (Pappers)
    chiffre_affaires: str = ""
    annee_bilan: str = ""
    source_ca: str = ""

    # Métadonnées matching
    confiance_match: int = 0
    statut_match: str = ""

    # Colonnes prospection (vides, à remplir manuellement)
    statut_prospection: str = ""
    notes: str = ""
    date_contact: str = ""

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)
