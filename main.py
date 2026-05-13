"""
Point d'entrée de l'application Heliantys Prospection.
Gère la configuration initiale et le lancement de la fenêtre principale.
"""

import sys
import json
import os
import logging

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor

# Configuration du logging global
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
    handlers=[
        logging.FileHandler("heliantys.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def charger_config() -> dict:
    """Charge la configuration locale du poste."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Impossible de lire config.json : {e}")
    return {}


def est_premier_lancement(config: dict) -> bool:
    """Retourne True si la configuration est incomplète (premier lancement)."""
    return not config.get("prenom") or not config.get("chemin_db")


def initialiser_base(config: dict) -> bool:
    """Initialise la base SQLite au chemin configuré. Retourne False si erreur critique."""
    import database

    chemin_db = config.get("chemin_db", "")
    if not chemin_db:
        chemin_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heliantys.db")
        config["chemin_db"] = chemin_db

    try:
        database.initialiser_base(chemin_db)
        logger.info(f"Base de données initialisée : {chemin_db}")
        return True
    except Exception as e:
        logger.error(f"Impossible d'initialiser la base : {e}")
        QMessageBox.critical(
            None,
            "Erreur base de données",
            f"Impossible d'ouvrir ou créer la base de données :\n{chemin_db}\n\nErreur : {e}"
        )
        return False


def proposer_import_excel(config: dict, app: QApplication) -> None:
    """Propose l'import du fichier Excel si la base est vide."""
    import database

    chemin_db = config.get("chemin_db", "")
    total = len(database.lister_pharmacies(chemin_db))

    if total > 0:
        return  # La base contient déjà des données

    # Cherche le fichier Excel à la racine
    excel_candidates = [
        f for f in os.listdir(os.path.dirname(os.path.abspath(__file__)))
        if f.endswith(".xlsx") and "pharma" in f.lower()
    ]

    if not excel_candidates:
        return

    chemin_excel = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), excel_candidates[0]
    )

    rep = QMessageBox.question(
        None,
        "Importer les données",
        f"La base de données est vide.\n\n"
        f"Voulez-vous importer le fichier :\n{excel_candidates[0]} ?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )

    if rep != QMessageBox.StandardButton.Yes:
        return

    from importer import importer_excel
    from PyQt6.QtWidgets import QProgressDialog

    progress = QProgressDialog("Import en cours…", "Annuler", 0, 100)
    progress.setWindowTitle("Import Excel")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)

    def callback(actuel, total, message):
        if total > 0:
            progress.setMaximum(total)
            progress.setValue(actuel)
            progress.setLabelText(message)
            app.processEvents()

    try:
        compteurs = importer_excel(chemin_db, chemin_excel, callback_progress=callback)
        progress.close()
        QMessageBox.information(
            None,
            "Import terminé",
            f"Import réussi :\n"
            f"• {compteurs['inserees']} pharmacies importées\n"
            f"• {compteurs['doublons']} doublons ignorés\n"
            f"• {compteurs['erreurs']} erreurs"
        )
    except Exception as e:
        progress.close()
        QMessageBox.warning(None, "Erreur d'import", str(e))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Heliantys Prospection")
    app.setOrganizationName("Heliantys")

    # Style global
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(250, 250, 252))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 250))
    app.setPalette(palette)

    # Chargement de la configuration
    config = charger_config()

    # Premier lancement : assistant de configuration
    if est_premier_lancement(config):
        from ui.setup_wizard import SetupWizard
        wizard = SetupWizard(CONFIG_PATH)
        if wizard.exec() != wizard.DialogCode.Accepted:
            sys.exit(0)
        config = charger_config()

    # Initialisation de la base de données
    if not initialiser_base(config):
        sys.exit(1)

    # Proposition d'import Excel si base vide
    proposer_import_excel(config, app)

    # Ouverture de la fenêtre principale
    from ui.main_window import MainWindow
    window = MainWindow(config, CONFIG_PATH)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
