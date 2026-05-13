"""
Fenêtre modale de scraping par région/département.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QProgressBar, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from scraper import REGIONS_DEPARTEMENTS, scraper_departement


class WorkerScraping(QThread):
    """Thread de scraping pour ne pas bloquer l'UI."""
    log = pyqtSignal(str)
    termine = pyqtSignal(dict)

    def __init__(self, db_path: str, departement: str):
        super().__init__()
        self.db_path = db_path
        self.departement = departement
        self.stop_flag = [False]

    def run(self):
        result = scraper_departement(
            self.db_path,
            self.departement,
            callback=lambda msg: self.log.emit(msg),
            stop_flag=self.stop_flag,
        )
        self.termine.emit(result)

    def arreter(self):
        self.stop_flag[0] = True


class ScrapingDialog(QDialog):
    """Boîte de dialogue pour lancer le scraping d'une région ou d'un département."""

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._worker = None
        self.setWindowTitle("Scraper une région")
        self.setMinimumSize(600, 500)
        self._construire_ui()

    def _construire_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        titre = QLabel("Scraping de pharmacies par région / département")
        titre.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        layout.addWidget(titre)

        desc = QLabel(
            "Lance la recherche sur l'API annuaire santé (data.gouv.fr) et Pages Jaunes.\n"
            "Les pharmacies trouvées sont ajoutées à la base sans créer de doublons."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ddd;")
        layout.addWidget(sep)

        # Sélection région → département
        grille = QHBoxLayout()

        layout_region = QVBoxLayout()
        layout_region.addWidget(QLabel("Région :"))
        self.combo_region = QComboBox()
        self.combo_region.setMinimumHeight(34)
        self.combo_region.addItem("-- Choisir une région --", "")
        for region in sorted(REGIONS_DEPARTEMENTS.keys()):
            self.combo_region.addItem(region, region)
        self.combo_region.currentIndexChanged.connect(self._on_region_change)
        layout_region.addWidget(self.combo_region)
        grille.addLayout(layout_region)

        layout_dept = QVBoxLayout()
        layout_dept.addWidget(QLabel("Département :"))
        self.combo_dept = QComboBox()
        self.combo_dept.setMinimumHeight(34)
        self.combo_dept.addItem("-- Choisir d'abord une région --", "")
        self.combo_dept.setEnabled(False)
        layout_dept.addWidget(self.combo_dept)
        grille.addLayout(layout_dept)

        layout.addLayout(grille)

        # Bouton lancer
        ligne_btn = QHBoxLayout()
        self.btn_lancer = QPushButton("Lancer le scraping")
        self.btn_lancer.setMinimumHeight(38)
        self.btn_lancer.setStyleSheet(
            "QPushButton { background: #1565C0; color: white; border-radius: 4px; font-weight: bold; padding: 0 20px; }"
            "QPushButton:hover { background: #0D47A1; }"
            "QPushButton:disabled { background: #aaa; }"
        )
        self.btn_lancer.setEnabled(False)
        self.btn_lancer.clicked.connect(self._lancer_ou_arreter)
        ligne_btn.addWidget(self.btn_lancer)
        ligne_btn.addStretch()
        layout.addLayout(ligne_btn)

        # Barre de progression
        self.barre = QProgressBar()
        self.barre.setRange(0, 0)  # Mode indéterminé
        self.barre.setVisible(False)
        self.barre.setMinimumHeight(18)
        layout.addWidget(self.barre)

        # Journal en temps réel
        lbl_log = QLabel("Journal :")
        lbl_log.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(lbl_log)

        self.journal = QTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setStyleSheet(
            "QTextEdit { background: #1a1a2e; color: #a8d8a8; font-family: monospace; "
            "font-size: 11px; border-radius: 4px; padding: 8px; }"
        )
        layout.addWidget(self.journal)

        # Bouton fermer
        ligne_fermer = QHBoxLayout()
        ligne_fermer.addStretch()
        self.btn_fermer = QPushButton("Fermer")
        self.btn_fermer.setMinimumWidth(100)
        self.btn_fermer.clicked.connect(self._fermer)
        ligne_fermer.addWidget(self.btn_fermer)
        layout.addLayout(ligne_fermer)

    def _on_region_change(self):
        region = self.combo_region.currentData()
        self.combo_dept.clear()
        self.combo_dept.setEnabled(False)
        self.btn_lancer.setEnabled(False)

        if not region:
            self.combo_dept.addItem("-- Choisir d'abord une région --", "")
            return

        depts = REGIONS_DEPARTEMENTS.get(region, [])
        self.combo_dept.addItem("-- Choisir un département --", "")
        for d in depts:
            self.combo_dept.addItem(f"Département {d}", d)
        self.combo_dept.setEnabled(True)
        self.combo_dept.currentIndexChanged.connect(self._on_dept_change)

    def _on_dept_change(self):
        dept = self.combo_dept.currentData()
        self.btn_lancer.setEnabled(bool(dept))

    def _lancer_ou_arreter(self):
        if self._worker and self._worker.isRunning():
            self._worker.arreter()
            self.btn_lancer.setText("Lancer le scraping")
            self.barre.setVisible(False)
            self._log("⏹ Scraping arrêté par l'utilisateur.")
            return

        dept = self.combo_dept.currentData()
        if not dept:
            return

        self._log(f"▶ Démarrage du scraping — Département {dept}")
        self.barre.setVisible(True)

        self._worker = WorkerScraping(self.db_path, dept)
        self._worker.log.connect(self._log)
        self._worker.termine.connect(self._on_termine)
        self._worker.start()

        self.btn_lancer.setText("Arrêter le scraping")

    def _log(self, message: str):
        self.journal.append(message)
        # Scroll vers le bas
        sb = self.journal.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_termine(self, compteurs: dict):
        self.barre.setVisible(False)
        self.btn_lancer.setText("Lancer le scraping")
        self._log(
            f"\n✅ Terminé — "
            f"{compteurs.get('inserees', 0)} insérées | "
            f"{compteurs.get('doublons', 0)} doublons | "
            f"{compteurs.get('erreurs', 0)} erreurs"
        )

    def _fermer(self):
        if self._worker and self._worker.isRunning():
            self._worker.arreter()
            self._worker.wait(2000)
        self.accept()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.arreter()
            self._worker.wait(2000)
        super().closeEvent(event)
