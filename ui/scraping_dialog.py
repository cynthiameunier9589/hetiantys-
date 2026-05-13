"""
Fenêtre modale de scraping par région/département.
Compatible Mac/Python 3.9+
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QProgressBar, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from scraper import REGIONS_DEPARTEMENTS, scraper_departement


class WorkerScraping(QThread):
    """Thread de scraping — compatible Mac."""

    log_msg = pyqtSignal(str)
    termine = pyqtSignal(dict)

    def __init__(self, db_path: str, departement: str):
        super().__init__()
        self.db_path = db_path
        self.departement = departement
        self._arreter = False
        self._stop_flag = [False]

    def run(self):
        def callback(msg: str):
            if not self._arreter:
                self.log_msg.emit(msg)

        result = scraper_departement(
            self.db_path,
            self.departement,
            callback=callback,
            stop_flag=self._stop_flag,
        )
        self.termine.emit(result)

    def arreter(self):
        self._arreter = True
        self._stop_flag[0] = True


class ScrapingDialog(QDialog):
    """Boite de dialogue pour lancer le scraping d'un département."""

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._worker = None
        self._nb_inserees = 0
        self.setWindowTitle("Scraper une region")
        self.setMinimumSize(640, 560)
        self._construire_ui()

    def _construire_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Titre
        titre = QLabel("Scraping de parapharmacies par region / departement")
        titre.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        layout.addWidget(titre)

        desc = QLabel(
            "Sources utilisees : OpenStreetMap (shop=chemist) + Pages Jaunes.\n"
            "Les parapharmacies trouvees sont ajoutees a la base sans creer de doublons."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #ddd; max-height: 1px;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Sélecteurs région → département
        sel_layout = QHBoxLayout()

        col_region = QVBoxLayout()
        col_region.addWidget(QLabel("Region :"))
        self.combo_region = QComboBox()
        self.combo_region.setMinimumHeight(32)
        self.combo_region.addItem("-- Choisir une region --", "")
        for region in sorted(REGIONS_DEPARTEMENTS.keys()):
            self.combo_region.addItem(region, region)
        self.combo_region.currentIndexChanged.connect(self._on_region_change)
        col_region.addWidget(self.combo_region)
        sel_layout.addLayout(col_region)

        col_dept = QVBoxLayout()
        col_dept.addWidget(QLabel("Departement :"))
        self.combo_dept = QComboBox()
        self.combo_dept.setMinimumHeight(32)
        self.combo_dept.addItem("-- Choisir d'abord une region --", "")
        self.combo_dept.setEnabled(False)
        col_dept.addWidget(self.combo_dept)
        sel_layout.addLayout(col_dept)

        layout.addLayout(sel_layout)

        # Bouton lancer
        self.btn_lancer = QPushButton("Lancer le scraping")
        self.btn_lancer.setMinimumHeight(38)
        self.btn_lancer.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; border-radius: 4px; "
            "font-weight: bold; padding: 0 20px; }"
            "QPushButton:pressed { background-color: #0D47A1; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self.btn_lancer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lancer.setEnabled(False)
        self.btn_lancer.clicked.connect(self._lancer_ou_arreter)
        layout.addWidget(self.btn_lancer)

        # Barre de progression indéterminée
        self.barre = QProgressBar()
        self.barre.setRange(0, 0)
        self.barre.setVisible(False)
        self.barre.setFixedHeight(14)
        layout.addWidget(self.barre)

        # Résumé résultat
        self.label_resultat = QLabel("")
        self.label_resultat.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #2e7d32; padding: 4px 0;"
        )
        self.label_resultat.setVisible(False)
        layout.addWidget(self.label_resultat)

        # Journal
        lbl_log = QLabel("Journal en temps reel :")
        lbl_log.setStyleSheet("font-weight: bold; color: #333; font-size: 12px;")
        layout.addWidget(lbl_log)

        self.journal = QTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setStyleSheet(
            "QTextEdit { background-color: #1a1a2e; color: #a8d8a8; "
            "font-family: monospace; font-size: 11px; "
            "border-radius: 4px; padding: 8px; }"
        )
        layout.addWidget(self.journal)

        # Bouton fermer
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_fermer = QPushButton("Fermer")
        self.btn_fermer.setMinimumWidth(100)
        self.btn_fermer.setMinimumHeight(34)
        self.btn_fermer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fermer.clicked.connect(self._fermer)
        btn_layout.addWidget(self.btn_fermer)
        layout.addLayout(btn_layout)

    def _on_region_change(self):
        region = self.combo_region.currentData()
        self.combo_dept.blockSignals(True)
        self.combo_dept.clear()
        self.combo_dept.setEnabled(False)
        self.btn_lancer.setEnabled(False)

        if not region:
            self.combo_dept.addItem("-- Choisir d'abord une region --", "")
            self.combo_dept.blockSignals(False)
            return

        depts = REGIONS_DEPARTEMENTS.get(region, [])
        self.combo_dept.addItem("-- Choisir un departement --", "")
        for d in depts:
            self.combo_dept.addItem(f"Departement {d}", d)
        self.combo_dept.setEnabled(True)
        self.combo_dept.blockSignals(False)
        self.combo_dept.currentIndexChanged.connect(self._on_dept_change)

    def _on_dept_change(self):
        dept = self.combo_dept.currentData()
        self.btn_lancer.setEnabled(bool(dept))

    def _lancer_ou_arreter(self):
        if self._worker and self._worker.isRunning():
            self._worker.arreter()
            self.btn_lancer.setText("Lancer le scraping")
            self.barre.setVisible(False)
            self._log("Scraping arrete par l'utilisateur.")
            return

        dept = self.combo_dept.currentData()
        if not dept:
            return

        self.journal.clear()
        self.label_resultat.setVisible(False)
        self._nb_inserees = 0

        self._log(f"Demarrage du scraping — Departement {dept}")
        self._log("Sources : OpenStreetMap + Pages Jaunes (parapharmacies)")
        self._log("Veuillez patienter, cela peut prendre 1 a 3 minutes...")
        self._log("")

        self.barre.setVisible(True)
        self.btn_lancer.setText("Arreter le scraping")
        self.btn_lancer.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; border-radius: 4px; "
            "font-weight: bold; padding: 0 20px; }"
            "QPushButton:pressed { background-color: #b71c1c; }"
        )

        self._worker = WorkerScraping(self.db_path, dept)
        self._worker.log_msg.connect(self._log)
        self._worker.termine.connect(self._on_termine)
        self._worker.start()

    def _log(self, message: str):
        self.journal.append(message)
        sb = self.journal.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_termine(self, compteurs: dict):
        self.barre.setVisible(False)
        self.btn_lancer.setText("Lancer le scraping")
        self.btn_lancer.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; border-radius: 4px; "
            "font-weight: bold; padding: 0 20px; }"
            "QPushButton:pressed { background-color: #0D47A1; }"
        )

        inserees = compteurs.get("inserees", 0)
        doublons = compteurs.get("doublons", 0)
        erreurs = compteurs.get("erreurs", 0)
        self._nb_inserees = inserees

        if inserees > 0:
            self.label_resultat.setText(
                f"Succes : {inserees} parapharmacies ajoutees a la base de donnees !"
            )
            self.label_resultat.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #2e7d32; padding: 4px 0;"
            )
        else:
            self.label_resultat.setText(
                f"Aucune parapharmacie trouvee. {doublons} doublons ignores. "
                f"Verifiez votre connexion Internet."
            )
            self.label_resultat.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #c62828; padding: 4px 0;"
            )
        self.label_resultat.setVisible(True)

    def _fermer(self):
        if self._worker and self._worker.isRunning():
            self._worker.arreter()
            self._worker.wait(3000)
        self.accept()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.arreter()
            self._worker.wait(3000)
        super().closeEvent(event)
