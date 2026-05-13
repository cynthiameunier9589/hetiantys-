"""
Vue liste des pharmacies avec filtres, tableau cliquable et actions groupées.
Version compatible Mac/Python 3.9+
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QMessageBox, QFileDialog, QFrame, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QBrush

import database
from database import STATUTS_DISPONIBLES

COULEUR_EN_CIBLE = QColor("#e8f5e9")
COULEUR_BORNE_POSEE = QColor("#e3f2fd")
COULEUR_PAS_INTERESSE = QColor("#eeeeee")
COULEUR_TEXTE_GRISE = QColor("#aaaaaa")


class WorkerEnrichissement(QThread):
    """Thread d'enrichissement par lot — compatible Mac."""

    progress = pyqtSignal(int, int, str)
    termine = pyqtSignal(dict)

    def __init__(self, db_path: str, api_token: str):
        super().__init__()
        self.db_path = db_path
        self.api_token = api_token
        self._arreter = False

    def run(self):
        from enricher import enrichir_lot
        result = enrichir_lot(
            self.db_path,
            api_token=self.api_token,
            callback_progress=self._callback,
            stop_flag=[False],
        )
        self.termine.emit(result)

    def _callback(self, actuel: int, total: int, message: str):
        if not self._arreter:
            self.progress.emit(actuel, total, message)

    def arreter(self):
        self._arreter = True


class ListePharmacies(QWidget):
    """Widget principal de liste des pharmacies."""

    pharmacie_selectionnee = pyqtSignal(int)

    def __init__(self, db_path: str, api_token: str = "", parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.api_token = api_token
        self._worker = None
        self._timer_filtre = QTimer()
        self._timer_filtre.setSingleShot(True)
        self._timer_filtre.timeout.connect(self.actualiser)
        self._construire_ui()

    def _construire_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # ── Titre + boutons ──
        barre = QHBoxLayout()
        titre = QLabel("Pharmacies")
        titre.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        barre.addWidget(titre)
        barre.addStretch()

        self.btn_scraper = QPushButton("Scraper une region")
        self.btn_scraper.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:pressed { background-color: #0D47A1; }"
        )
        self.btn_scraper.setCursor(Qt.CursorShape.PointingHandCursor)
        barre.addWidget(self.btn_scraper)

        self.btn_enrichir_lot = QPushButton("Enrichissement par lot")
        self.btn_enrichir_lot.setStyleSheet(
            "QPushButton { background-color: #6A1B9A; color: white; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:pressed { background-color: #4A148C; }"
        )
        self.btn_enrichir_lot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_enrichir_lot.clicked.connect(self._lancer_enrichissement_lot)
        barre.addWidget(self.btn_enrichir_lot)

        self.btn_exporter = QPushButton("Exporter")
        self.btn_exporter.setStyleSheet(
            "QPushButton { background-color: #37474F; color: white; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:pressed { background-color: #263238; }"
        )
        self.btn_exporter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_exporter.clicked.connect(self._exporter)
        barre.addWidget(self.btn_exporter)

        layout.addLayout(barre)

        # ── Filtres ──
        panel = QFrame()
        panel.setStyleSheet("QFrame { background-color: #f5f5f5; border-radius: 6px; }")
        f_layout = QHBoxLayout(panel)
        f_layout.setContentsMargins(10, 8, 10, 8)
        f_layout.setSpacing(8)

        self.input_recherche = QLineEdit()
        self.input_recherche.setPlaceholderText("Rechercher par nom ou ville...")
        self.input_recherche.setMinimumHeight(30)
        self.input_recherche.textChanged.connect(lambda: self._timer_filtre.start(300))
        f_layout.addWidget(self.input_recherche, 3)

        self.combo_dept = QComboBox()
        self.combo_dept.setMinimumHeight(30)
        self.combo_dept.addItem("Tous les departements", "")
        self.combo_dept.currentIndexChanged.connect(self.actualiser)
        f_layout.addWidget(self.combo_dept, 2)

        self.combo_statut = QComboBox()
        self.combo_statut.setMinimumHeight(30)
        self.combo_statut.addItem("Tous les statuts", "")
        for s in STATUTS_DISPONIBLES:
            self.combo_statut.addItem(s, s)
        self.combo_statut.currentIndexChanged.connect(self.actualiser)
        f_layout.addWidget(self.combo_statut, 2)

        self.check_cible = QCheckBox("En cible uniquement")
        self.check_cible.stateChanged.connect(self.actualiser)
        f_layout.addWidget(self.check_cible)

        self.check_non_enrichies = QCheckBox("Non enrichies")
        self.check_non_enrichies.stateChanged.connect(self.actualiser)
        f_layout.addWidget(self.check_non_enrichies)

        layout.addWidget(panel)

        self.label_compteur = QLabel("")
        self.label_compteur.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self.label_compteur)

        # ── Tableau ──
        self.tableau = QTableWidget()
        self.tableau.setColumnCount(11)
        self.tableau.setHorizontalHeaderLabels([
            "Nom", "Ville", "CP", "Dpt", "Telephone", "Email",
            "CA", "Statut", "Cible", "Enrichi", "Action"
        ])
        self.tableau.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableau.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableau.setAlternatingRowColors(False)
        self.tableau.verticalHeader().setVisible(False)
        self.tableau.setShowGrid(True)
        self.tableau.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tableau.setColumnWidth(2, 60)
        self.tableau.setColumnWidth(3, 50)
        self.tableau.setColumnWidth(8, 55)
        self.tableau.setColumnWidth(9, 65)
        self.tableau.setColumnWidth(10, 80)
        self.tableau.cellClicked.connect(self._on_clic)
        layout.addWidget(self.tableau)

        # ── Barre de progression ──
        self.barre_progress = QProgressBar()
        self.barre_progress.setVisible(False)
        self.barre_progress.setFixedHeight(18)
        layout.addWidget(self.barre_progress)

        self.label_progress = QLabel("")
        self.label_progress.setVisible(False)
        self.label_progress.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.label_progress)

    def actualiser(self):
        """Recharge le tableau avec les filtres actifs."""
        try:
            depts = database.get_departements(self.db_path)
            dept_actuel = self.combo_dept.currentData()
            self.combo_dept.blockSignals(True)
            self.combo_dept.clear()
            self.combo_dept.addItem("Tous les departements", "")
            for d in depts:
                self.combo_dept.addItem(d, d)
            if dept_actuel:
                idx = self.combo_dept.findData(dept_actuel)
                if idx >= 0:
                    self.combo_dept.setCurrentIndex(idx)
            self.combo_dept.blockSignals(False)

            pharmacies = database.lister_pharmacies(
                self.db_path,
                recherche=self.input_recherche.text().strip(),
                departement=self.combo_dept.currentData() or "",
                statut=self.combo_statut.currentData() or "",
                en_cible_only=self.check_cible.isChecked(),
                non_enrichies_only=self.check_non_enrichies.isChecked(),
            )
        except Exception:
            return

        self.label_compteur.setText(f"{len(pharmacies)} pharmacie(s) affichee(s)")
        self.tableau.setRowCount(0)

        for pharm in pharmacies:
            row = self.tableau.rowCount()
            self.tableau.insertRow(row)

            en_cible = bool(pharm["en_cible"])
            statut = pharm["statut"] or ""

            valeurs = [
                pharm["nom"] or "",
                pharm["ville"] or "",
                pharm["code_postal"] or "",
                pharm["departement"] or "",
                pharm["telephone"] or "",
                pharm["email"] or "",
                pharm["ca_tranche"] or "",
                statut,
                "Oui" if en_cible else "",
                "Oui" if pharm["enrichi"] else "",
            ]

            for col, val in enumerate(valeurs):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col in (7, 8, 9):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tableau.setItem(row, col, item)

            # Stocker l'id pharmacie dans la première cellule
            self.tableau.item(row, 0).setData(Qt.ItemDataRole.UserRole, pharm["id"])

            # Bouton enrichir
            btn = QPushButton("Enrichir")
            btn.setStyleSheet(
                "QPushButton { font-size: 11px; padding: 2px 6px; "
                "background-color: #7B1FA2; color: white; border-radius: 3px; }"
                "QPushButton:pressed { background-color: #4A148C; }"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("pid", pharm["id"])
            btn.clicked.connect(self._enrichir_une)
            self.tableau.setCellWidget(row, 10, btn)

            # Couleur de ligne
            couleur = None
            if statut == "Borne posee":
                couleur = COULEUR_BORNE_POSEE
            elif statut == "Pas interesse":
                couleur = COULEUR_PAS_INTERESSE
            elif en_cible:
                couleur = COULEUR_EN_CIBLE

            if couleur:
                for col in range(10):
                    item = self.tableau.item(row, col)
                    if item:
                        item.setBackground(QBrush(couleur))
                        if statut == "Pas interesse":
                            item.setForeground(QBrush(COULEUR_TEXTE_GRISE))

        self.tableau.resizeRowsToContents()

    def _on_clic(self, row: int, col: int):
        if col == 10:
            return
        item = self.tableau.item(row, 0)
        if item:
            pid = item.data(Qt.ItemDataRole.UserRole)
            if pid:
                self.pharmacie_selectionnee.emit(pid)

    def _enrichir_une(self):
        btn = self.sender()
        if not btn:
            return
        pid = btn.property("pid")
        if not pid:
            return
        try:
            pharm = database.get_pharmacie(self.db_path, pid)
            if pharm:
                from enricher import enrichir_pharmacie
                enrichir_pharmacie(self.db_path, dict(pharm), api_token=self.api_token)
                self.actualiser()
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Enrichissement impossible :\n{e}")

    def _lancer_enrichissement_lot(self):
        if self._worker and self._worker.isRunning():
            self._worker.arreter()
            self.btn_enrichir_lot.setText("Enrichissement par lot")
            self.barre_progress.setVisible(False)
            self.label_progress.setVisible(False)
            return

        self._worker = WorkerEnrichissement(self.db_path, self.api_token)
        self._worker.progress.connect(self._on_progress)
        self._worker.termine.connect(self._on_enrichissement_termine)
        self._worker.start()

        self.btn_enrichir_lot.setText("Arreter l'enrichissement")
        self.barre_progress.setVisible(True)
        self.barre_progress.setValue(0)
        self.label_progress.setVisible(True)

    def _on_progress(self, actuel: int, total: int, message: str):
        if total > 0:
            self.barre_progress.setMaximum(total)
            self.barre_progress.setValue(actuel)
        self.label_progress.setText(message)

    def _on_enrichissement_termine(self, compteurs: dict):
        self.barre_progress.setVisible(False)
        self.label_progress.setVisible(False)
        self.btn_enrichir_lot.setText("Enrichissement par lot")
        self.actualiser()
        QMessageBox.information(
            self, "Enrichissement termine",
            f"Enrichies : {compteurs.get('enrichies', 0)}\n"
            f"Sans resultat : {compteurs.get('sans_resultat', 0)}\n"
            f"Erreurs : {compteurs.get('erreurs', 0)}"
        )

    def _exporter(self):
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter", "", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not chemin:
            return
        try:
            pharmacies = database.lister_pharmacies(
                self.db_path,
                recherche=self.input_recherche.text().strip(),
                departement=self.combo_dept.currentData() or "",
                statut=self.combo_statut.currentData() or "",
                en_cible_only=self.check_cible.isChecked(),
                non_enrichies_only=self.check_non_enrichies.isChecked(),
            )
            if chemin.endswith(".csv"):
                _exporter_csv(pharmacies, chemin)
            else:
                _exporter_excel(pharmacies, chemin)
            QMessageBox.information(self, "Export reussi", f"Fichier enregistre :\n{chemin}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))

    def set_db_path(self, db_path: str):
        self.db_path = db_path
        self.actualiser()

    def set_api_token(self, token: str):
        self.api_token = token


def _exporter_excel(pharmacies, chemin: str):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pharmacies"
    ws.append([
        "Nom", "Adresse", "Ville", "CP", "Departement", "Telephone", "Fax",
        "Email", "Nom decidant", "Prenom decidant", "Tel decidant", "Email decidant",
        "CA tranche", "CA estime (EUR)", "En cible", "Statut", "Source", "Enrichi",
    ])
    for p in pharmacies:
        ws.append([
            p["nom"], p["adresse"], p["ville"], p["code_postal"], p["departement"],
            p["telephone"], p["fax"], p["email"],
            p["nom_decidant"], p["prenom_decidant"], p["telephone_decidant"], p["email_decidant"],
            p["ca_tranche"], p["ca_value"],
            "Oui" if p["en_cible"] else "Non",
            p["statut"], p["source"],
            "Oui" if p["enrichi"] else "Non",
        ])
    wb.save(chemin)


def _exporter_csv(pharmacies, chemin: str):
    import csv
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Nom", "Adresse", "Ville", "CP", "Departement", "Telephone", "Email", "CA tranche", "En cible", "Statut"])
        for p in pharmacies:
            writer.writerow([
                p["nom"], p["adresse"], p["ville"], p["code_postal"],
                p["departement"], p["telephone"], p["email"],
                p["ca_tranche"], "Oui" if p["en_cible"] else "Non", p["statut"],
            ])
