"""
Gestion de la base de données SQLite pour l'application Heliantys.
Création des tables, fonctions CRUD pour pharmacies, notes, historique et paramètres.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple


def get_connection(db_path: str) -> sqlite3.Connection:
    """Retourne une connexion SQLite avec support des clés étrangères."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialiser_base(db_path: str) -> None:
    """Crée toutes les tables si elles n'existent pas déjà."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None

    with get_connection(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pharmacies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                adresse TEXT,
                ville TEXT,
                code_postal TEXT,
                departement TEXT,
                telephone TEXT,
                fax TEXT,
                email TEXT,
                nom_decidant TEXT,
                prenom_decidant TEXT,
                telephone_decidant TEXT,
                email_decidant TEXT,
                ca_tranche TEXT,
                ca_value REAL,
                en_cible INTEGER DEFAULT 0,
                statut TEXT DEFAULT 'À contacter',
                date_creation TEXT,
                date_modification TEXT,
                date_dernier_contact TEXT,
                enrichi INTEGER DEFAULT 0,
                source TEXT DEFAULT 'manuel',
                UNIQUE(nom, ville, code_postal)
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pharmacie_id INTEGER NOT NULL,
                contenu TEXT NOT NULL,
                date_heure TEXT NOT NULL,
                auteur TEXT,
                FOREIGN KEY (pharmacie_id) REFERENCES pharmacies(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS historique_statuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pharmacie_id INTEGER NOT NULL,
                ancien_statut TEXT,
                nouveau_statut TEXT,
                date_heure TEXT NOT NULL,
                auteur TEXT,
                FOREIGN KEY (pharmacie_id) REFERENCES pharmacies(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                cle TEXT PRIMARY KEY,
                valeur TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_pharmacies_ville ON pharmacies(ville);
            CREATE INDEX IF NOT EXISTS idx_pharmacies_departement ON pharmacies(departement);
            CREATE INDEX IF NOT EXISTS idx_pharmacies_statut ON pharmacies(statut);
            CREATE INDEX IF NOT EXISTS idx_pharmacies_en_cible ON pharmacies(en_cible);
            CREATE INDEX IF NOT EXISTS idx_notes_pharmacie ON notes(pharmacie_id);
            CREATE INDEX IF NOT EXISTS idx_historique_pharmacie ON historique_statuts(pharmacie_id);
        """)


# ─── PHARMACIES ────────────────────────────────────────────────────────────────

def inserer_pharmacie(db_path: str, data: Dict[str, Any]) -> Optional[int]:
    """
    Insère une pharmacie en ignorant si le doublon (nom+ville+cp) existe déjà.
    Retourne l'id inséré, ou None si doublon.
    """
    now = datetime.now().isoformat()
    data.setdefault("date_creation", now)
    data.setdefault("date_modification", now)
    data.setdefault("statut", "À contacter")
    data.setdefault("enrichi", 0)
    data.setdefault("source", "manuel")

    sql = """
        INSERT OR IGNORE INTO pharmacies
            (nom, adresse, ville, code_postal, departement, telephone, fax, email,
             nom_decidant, prenom_decidant, telephone_decidant, email_decidant,
             ca_tranche, ca_value, en_cible, statut, date_creation, date_modification,
             date_dernier_contact, enrichi, source)
        VALUES
            (:nom, :adresse, :ville, :code_postal, :departement, :telephone, :fax, :email,
             :nom_decidant, :prenom_decidant, :telephone_decidant, :email_decidant,
             :ca_tranche, :ca_value, :en_cible, :statut, :date_creation, :date_modification,
             :date_dernier_contact, :enrichi, :source)
    """
    defaults = {k: None for k in [
        "adresse", "ville", "code_postal", "departement", "telephone", "fax", "email",
        "nom_decidant", "prenom_decidant", "telephone_decidant", "email_decidant",
        "ca_tranche", "ca_value", "en_cible", "date_dernier_contact"
    ]}
    defaults.update(data)

    with get_connection(db_path) as conn:
        cur = conn.execute(sql, defaults)
        return cur.lastrowid if cur.rowcount > 0 else None


def mettre_a_jour_pharmacie(db_path: str, pharmacie_id: int, data: Dict[str, Any]) -> None:
    """Met à jour les champs fournis d'une pharmacie."""
    data["date_modification"] = datetime.now().isoformat()
    data["id"] = pharmacie_id

    champs = [k for k in data if k not in ("id",)]
    set_clause = ", ".join(f"{c} = :{c}" for c in champs)

    with get_connection(db_path) as conn:
        conn.execute(f"UPDATE pharmacies SET {set_clause} WHERE id = :id", data)


def mettre_a_jour_statut(db_path: str, pharmacie_id: int, nouveau_statut: str, auteur: str) -> None:
    """Change le statut et enregistre dans l'historique."""
    now = datetime.now().isoformat()

    with get_connection(db_path) as conn:
        row = conn.execute("SELECT statut FROM pharmacies WHERE id = ?", (pharmacie_id,)).fetchone()
        if not row:
            return
        ancien_statut = row["statut"]

        conn.execute(
            "UPDATE pharmacies SET statut = ?, date_modification = ?, date_dernier_contact = ? WHERE id = ?",
            (nouveau_statut, now, now, pharmacie_id)
        )
        conn.execute(
            "INSERT INTO historique_statuts (pharmacie_id, ancien_statut, nouveau_statut, date_heure, auteur) VALUES (?, ?, ?, ?, ?)",
            (pharmacie_id, ancien_statut, nouveau_statut, now, auteur)
        )


def get_pharmacie(db_path: str, pharmacie_id: int) -> Optional[sqlite3.Row]:
    """Retourne une pharmacie par son id."""
    with get_connection(db_path) as conn:
        return conn.execute("SELECT * FROM pharmacies WHERE id = ?", (pharmacie_id,)).fetchone()


def lister_pharmacies(
    db_path: str,
    recherche: str = "",
    departement: str = "",
    statut: str = "",
    en_cible_only: bool = False,
    non_enrichies_only: bool = False,
    limit: int = 0,
    offset: int = 0
) -> List[sqlite3.Row]:
    """Retourne la liste des pharmacies avec filtres optionnels."""
    conditions = []
    params: List[Any] = []

    if recherche:
        conditions.append("(LOWER(nom) LIKE ? OR LOWER(ville) LIKE ?)")
        like = f"%{recherche.lower()}%"
        params += [like, like]
    if departement:
        conditions.append("departement = ?")
        params.append(departement)
    if statut:
        conditions.append("statut = ?")
        params.append(statut)
    if en_cible_only:
        conditions.append("en_cible = 1")
    if non_enrichies_only:
        conditions.append("enrichi = 0")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"SELECT * FROM pharmacies {where} ORDER BY nom ASC"

    if limit > 0:
        sql += f" LIMIT {limit} OFFSET {offset}"

    with get_connection(db_path) as conn:
        return conn.execute(sql, params).fetchall()


def compter_pharmacies(db_path: str, **filtres) -> int:
    """Retourne le nombre de pharmacies correspondant aux filtres."""
    return len(lister_pharmacies(db_path, **filtres))


def get_departements(db_path: str) -> List[str]:
    """Retourne la liste des départements présents dans la base."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT departement FROM pharmacies WHERE departement IS NOT NULL ORDER BY departement"
        ).fetchall()
    return [r[0] for r in rows]


def get_statistiques(db_path: str) -> Dict[str, Any]:
    """Retourne les statistiques globales pour le tableau de bord."""
    with get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM pharmacies").fetchone()[0]
        en_cible = conn.execute("SELECT COUNT(*) FROM pharmacies WHERE en_cible = 1").fetchone()[0]
        hors_cible = total - en_cible
        non_contactees = conn.execute(
            "SELECT COUNT(*) FROM pharmacies WHERE statut = 'À contacter'"
        ).fetchone()[0]

        par_statut = conn.execute(
            "SELECT statut, COUNT(*) as nb FROM pharmacies GROUP BY statut ORDER BY nb DESC"
        ).fetchall()

        top_depts = conn.execute("""
            SELECT departement, COUNT(*) as nb
            FROM pharmacies
            WHERE en_cible = 1 AND departement IS NOT NULL
            GROUP BY departement
            ORDER BY nb DESC
            LIMIT 5
        """).fetchall()

        dernieres_modifs = conn.execute("""
            SELECT * FROM pharmacies
            ORDER BY date_modification DESC
            LIMIT 10
        """).fetchall()

    return {
        "total": total,
        "en_cible": en_cible,
        "hors_cible": hors_cible,
        "non_contactees": non_contactees,
        "par_statut": [(r["statut"], r["nb"]) for r in par_statut],
        "top_departements": [(r["departement"], r["nb"]) for r in top_depts],
        "dernieres_modifications": dernieres_modifs,
    }


def supprimer_pharmacie(db_path: str, pharmacie_id: int) -> None:
    """Supprime une pharmacie et ses données associées."""
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM pharmacies WHERE id = ?", (pharmacie_id,))


# ─── NOTES ─────────────────────────────────────────────────────────────────────

def ajouter_note(db_path: str, pharmacie_id: int, contenu: str, auteur: str) -> int:
    """Ajoute une note horodatée pour une pharmacie."""
    now = datetime.now().isoformat()
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO notes (pharmacie_id, contenu, date_heure, auteur) VALUES (?, ?, ?, ?)",
            (pharmacie_id, contenu, now, auteur)
        )
        # Mise à jour de la date de modification de la pharmacie
        conn.execute(
            "UPDATE pharmacies SET date_modification = ?, date_dernier_contact = ? WHERE id = ?",
            (now, now, pharmacie_id)
        )
        return cur.lastrowid


def get_notes(db_path: str, pharmacie_id: int) -> List[sqlite3.Row]:
    """Retourne toutes les notes d'une pharmacie, ordre chronologique."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM notes WHERE pharmacie_id = ? ORDER BY date_heure ASC",
            (pharmacie_id,)
        ).fetchall()


# ─── HISTORIQUE STATUTS ────────────────────────────────────────────────────────

def get_historique_statuts(db_path: str, pharmacie_id: int) -> List[sqlite3.Row]:
    """Retourne l'historique des changements de statut d'une pharmacie."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM historique_statuts WHERE pharmacie_id = ? ORDER BY date_heure ASC",
            (pharmacie_id,)
        ).fetchall()


# ─── SETTINGS ──────────────────────────────────────────────────────────────────

def get_setting(db_path: str, cle: str, defaut: str = "") -> str:
    """Lit un paramètre depuis la table settings."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT valeur FROM settings WHERE cle = ?", (cle,)).fetchone()
    return row[0] if row else defaut


def set_setting(db_path: str, cle: str, valeur: str) -> None:
    """Enregistre un paramètre dans la table settings."""
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (cle, valeur) VALUES (?, ?)",
            (cle, valeur)
        )


def pharmacie_existe(db_path: str, nom: str, ville: str, code_postal: str) -> bool:
    """Vérifie si une pharmacie existe déjà dans la base."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM pharmacies WHERE nom = ? AND ville = ? AND code_postal = ?",
            (nom, ville, code_postal)
        ).fetchone()
    return row is not None


STATUTS_DISPONIBLES = [
    "À contacter",
    "À rappeler",
    "Mail envoyé",
    "RDV pris",
    "Borne posée",
    "Pas intéressé",
]

TRANCHES_EN_CIBLE = {
    "5 A 6 MF", "6 A 7 MF", "7 A 8 MF", "8 A 10 MF",
    "10 A 12 MF", "12 A 16 MF", "16 MF ET PLUS"
}

CA_VALEURS_ESTIMEES = {
    "5 A 6 MF": 5_500_000,
    "6 A 7 MF": 6_500_000,
    "7 A 8 MF": 7_500_000,
    "8 A 10 MF": 9_000_000,
    "10 A 12 MF": 11_000_000,
    "12 A 16 MF": 14_000_000,
    "16 MF ET PLUS": 18_000_000,
    "1 A 2 MF": 1_500_000,
    "2 A 3 MF": 2_500_000,
    "3 A 4 MF": 3_500_000,
    "4 A 5 MF": 4_500_000,
}
