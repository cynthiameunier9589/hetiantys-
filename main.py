"""
Point d'entrée de l'application Heliantys Prospection.
Compatible Mac/Python 3.9+ — pas de palette personnalisée qui serait ignorée par macOS.
"""

import sys
import json
import os
import logging

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt

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
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Impossible de lire config.json : {e}")
    return {}


def est_premier_lancement(config: dict) -> bool:
    return not config.get("prenom") or not config.get("chemin_db")


def initialiser_base(config: dict) -> bool:
    import database

    chemin_db = config.get("chemin_db", "")
    if not chemin_db:
        chemin_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heliantys.db")
        config["chemin_db"] = chemin_db

    try:
        database.initialiser_base(chemin_db)
        logger.info(f"Base de donnees initialisee : {chemin_db}")
        return True
    except Exception as e:
        logger.error(f"Impossible d'initialiser la base : {e}")
        QMessageBox.critical(
            None,
            "Erreur base de donnees",
            f"Impossible d'ouvrir ou creer la base :\n{chemin_db}\n\nErreur : {e}"
        )
        return False


def proposer_import_excel(config: dict, app: QApplication) -> None:
    import database

    chemin_db = config.get("chemin_db", "")
    try:
        total = len(database.lister_pharmacies(chemin_db))
    except Exception:
        return

    if total > 0:
        return

    # Cherche un fichier Excel de pharmacies à la racine
    racine = os.path.dirname(os.path.abspath(__file__))
    excel_candidates = [
        f for f in os.listdir(racine)
        if f.endswith(".xlsx") and "pharma" in f.lower()
    ]

    if not excel_candidates:
        return

    chemin_excel = os.path.join(racine, excel_candidates[0])

    rep = QMessageBox.question(
        None,
        "Importer les donnees",
        f"La base est vide.\nVoulez-vous importer :\n{excel_candidates[0]} ?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if rep != QMessageBox.StandardButton.Yes:
        return

    from importer import importer_excel

    progress = QProgressDialog("Import en cours...", "Annuler", 0, 100)
    progress.setWindowTitle("Import Excel")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    progress.show()

    def callback(actuel, total_rows, message):
        if total_rows > 0:
            progress.setMaximum(total_rows)
            progress.setValue(actuel)
            progress.setLabelText(message)
            app.processEvents()

    try:
        compteurs = importer_excel(chemin_db, chemin_excel, callback_progress=callback)
        progress.close()
        QMessageBox.information(
            None,
            "Import termine",
            f"Import reussi :\n"
            f"• {compteurs['inserees']} pharmacies importees\n"
            f"• {compteurs['doublons']} doublons ignores\n"
            f"• {compteurs['erreurs']} erreurs"
        )
    except Exception as e:
        progress.close()
        QMessageBox.warning(None, "Erreur d'import", str(e))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Heliantys Prospection")
    app.setOrganizationName("Heliantys")
    app.setStyle("Fusion")

    config = charger_config()

    if est_premier_lancement(config):
        from ui.setup_wizard import SetupWizard
        wizard = SetupWizard(CONFIG_PATH)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        config = charger_config()

    if not initialiser_base(config):
        sys.exit(1)

    proposer_import_excel(config, app)

    from ui.main_window import MainWindow
    window = MainWindow(config, CONFIG_PATH)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
