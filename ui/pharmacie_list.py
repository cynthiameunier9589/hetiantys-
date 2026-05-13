"""
Vue liste des pharmacies avec filtres, tableau cliquable et actions groupées.
"""

import threading
from typing import Optional, Callable

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
COULEUR_TEXTE_GRISE = QColor("#999999")


class WorkerEnrichissement(QThread):
    """Thread d'enrichissement par lot."""
    progress = pyqtSignal(int, int, str)
    termine = pyqtSignal(dict)

    def __init__(self, db_path: str, api_token: str):
        super().__init__()
        self.db_path = db_path
        self.api_token = api_token
        self.stop_flag = [False]

    def run(self):
        from enricher import enrichir_lot
        result = enrichir_lot(
            self.db_path,
            api_token=self.api_token,
            callback_progress=lambda a, t, m: self.progress.emit(a, t, m),
            stop_flag=self.stop_flag,
        )
        self.termine.emit(result)

    def arreter(self):
        self.stop_flag[0] = True


class ListePharmacies(QWidget):
    """Widget principal de liste des pharmacies."""

    pharmacie_selectionnee = pyqtSignal(int)

    def __init__(self, db_path: str, api_token: str = "", parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.api_token = api_token
        self._worker = None
        self._construire_ui()
        self._charger_departements()
        self.actualiser()

    def _construire_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # ── Titre + boutons d'action ──
        barre_titre = QHBoxLayout()
        titre = QLabel("Pharmacies")
        titre.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        barre_titre.addWidget(titre)
        barre_titre.addStretch()

        self.btn_scraper = QPushButton("Scraper une région")
        self.btn_scraper.setStyleSheet("QPushButton { background: #1565C0; color: white; border-radius: 4px; padding: 6px 12px; }")
        barre_titre.addWidget(self.btn_scraper)

        self.btn_enrichir_lot = QPushButton("Enrichissement par lot")
        self.btn_enrichir_lot.setStyleSheet("QPushButton { background: #6A1B9A; color: white; border-radius: 4px; padding: 6px 12px; }")
        self.btn_enrichir_lot.clicked.connect(self._lancer_enrichissement_lot)
        barre_titre.addWidget(self.btn_enrichir_lot)

        self.btn_exporter = QPushButton("Exporter")
        self.btn_exporter.setStyleSheet("QPushButton { background: #37474F; color: white; border-radius: 4px; padding: 6px 12px; }")
        self.btn_exporter.clicked.connect(self._exporter)
        barre_titre.addWidget(self.btn_exporter)

        layout.addLayout(barre_titre)

        # ── Filtres ──
        panel_filtres = QFrame()
        panel_filtres.setStyleSheet("QFrame { background: #f5f5f5; border-radius: 6px; padding: 4px; }")
        filtres_layout = QHBoxLayout(panel_filtres)
        filtres_layout.setContentsMargins(8, 8, 8, 8)
        filtres_layout.setSpacing(8)

        self.input_recherche = QLineEdit()
        self.input_recherche.setPlaceholderText("Rechercher par nom ou ville…")
        self.input_recherche.setMinimumHeight(32)
        self.input_recherche.textChanged.connect(self._on_filtre_change)
        filtres_layout.addWidget(self.input_recherche, 3)

        self.combo_dept = QComboBox()
        self.combo_dept.setMinimumHeight(32)
        self.combo_dept.addItem("Tous les départements", "")
        self.combo_dept.currentIndexChanged.connect(self._on_filtre_change)
        filtres_layout.addWidget(self.combo_dept, 2)

        self.combo_statut = QComboBox()
        self.combo_statut.setMinimumHeight(32)
        self.combo_statut.addItem("Tous les statuts", "")
        for s in STATUTS_DISPONIBLES:
            self.combo_statut.addItem(s, s)
        self.combo_statut.currentIndexChanged.connect(self._on_filtre_change)
        filtres_layout.addWidget(self.combo_statut, 2)

        self.check_cible = QCheckBox("En cible uniquement")
        self.check_cible.stateChanged.connect(self._on_filtre_change)
        filtres_layout.addWidget(self.check_cible)

        self.check_non_enrichies = QCheckBox("Non enrichies uniquement")
        self.check_non_enrichies.stateChanged.connect(self._on_filtre_change)
        filtres_layout.addWidget(self.check_non_enrichies)

        layout.addWidget(panel_filtres)

        # ── Compteur ──
        self.label_compteur = QLabel("")
        self.label_compteur.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self.label_compteur)

        # ── Tableau ──
        self.tableau = QTableWidget()
        self.tableau.setColumnCount(11)
        self.tableau.setHorizontalHeaderLabels([
            "Nom", "Ville", "CP", "Dpt", "Téléphone", "Email",
            "CA", "Statut", "En cible", "Enrichi", "Actions"
        ])
        self.tableau.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableau.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableau.setAlternatingRowColors(False)
        self.tableau.verticalHeader().setVisible(False)
        self.tableau.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tableau.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.tableau.setColumnWidth(10, 90)
        self.tableau.doubleClicked.connect(self._on_double_clic)
        self.tableau.cellClicked.connect(self._on_clic_cellule)
        layout.addWidget(self.tableau)

        # ── Barre de progression enrichissement ──
        self.barre_progress = QProgressBar()
        self.barre_progress.setVisible(False)
        self.barre_progress.setMinimumHeight(20)
        layout.addWidget(self.barre_progress)

        self.label_progress = QLabel("")
        self.label_progress.setVisible(False)
        self.label_progress.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.label_progress)

    def _charger_departements(self):
        depts = database.get_departements(self.db_path)
        self.combo_dept.clear()
        self.combo_dept.addItem("Tous les départements", "")
        for d in depts:
            self.combo_dept.addItem(d, d)

    def _on_filtre_change(self):
        QTimer.singleShot(200, self.actualiser)

    def actualiser(self):
        """Recharge le tableau avec les filtres actifs."""
        self._charger_departements()
        pharmacies = database.lister_pharmacies(
            self.db_path,
            recherche=self.input_recherche.text().strip(),
            departement=self.combo_dept.currentData() or "",
            statut=self.combo_statut.currentData() or "",
            en_cible_only=self.check_cible.isChecked(),
            non_enrichies_only=self.check_non_enrichies.isChecked(),
        )

        self.label_compteur.setText(f"{len(pharmacies)} pharmacie(s) affichée(s)")
        self.tableau.setRowCount(0)

        for pharm in pharmacies:
            row = self.tableau.rowCount()
            self.tableau.insertRow(row)

            en_cible = bool(pharm["en_cible"])
            statut = pharm["statut"] or ""
            enrichi = bool(pharm["enrichi"])

            self.tableau.setItem(row, 0, QTableWidgetItem(pharm["nom"] or ""))
            self.tableau.setItem(row, 1, QTableWidgetItem(pharm["ville"] or ""))
            self.tableau.setItem(row, 2, QTableWidgetItem(pharm["code_postal"] or ""))
            self.tableau.setItem(row, 3, QTableWidgetItem(pharm["departement"] or ""))
            self.tableau.setItem(row, 4, QTableWidgetItem(pharm["telephone"] or ""))
            self.tableau.setItem(row, 5, QTableWidgetItem(pharm["email"] or ""))
            self.tableau.setItem(row, 6, QTableWidgetItem(pharm["ca_tranche"] or ""))

            item_statut = QTableWidgetItem(statut)
            item_statut.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tableau.setItem(row, 7, item_statut)

            item_cible = QTableWidgetItem("✓" if en_cible else "")
            item_cible.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tableau.setItem(row, 8, item_cible)

            item_enrichi = QTableWidgetItem("✓" if enrichi else "")
            item_enrichi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tableau.setItem(row, 9, item_enrichi)

            # Bouton enrichir
            btn = QPushButton("Enrichir")
            btn.setStyleSheet("QPushButton { font-size: 11px; padding: 2px 8px; background: #7B1FA2; color: white; border-radius: 3px; }")
            btn.setProperty("pharmacie_id", pharm["id"])
            btn.clicked.connect(self._enrichir_une)
            self.tableau.setCellWidget(row, 10, btn)

            # Stocker l'id dans la ligne
            self.tableau.item(row, 0).setData(Qt.ItemDataRole.UserRole, pharm["id"])

            # Couleur de la ligne
            couleur = None
            if statut == "Borne posée":
                couleur = COULEUR_BORNE_POSEE
            elif statut == "Pas intéressé":
                couleur = COULEUR_PAS_INTERESSE
            elif en_cible:
                couleur = COULEUR_EN_CIBLE

            if couleur:
                for col in range(10):
                    item = self.tableau.item(row, col)
                    if item:
                        item.setBackground(QBrush(couleur))
                        if statut == "Pas intéressé":
                            item.setForeground(QBrush(COULEUR_TEXTE_GRISE))

        self.tableau.resizeRowsToContents()

    def _on_double_clic(self, index):
        row = index.row()
        item = self.tableau.item(row, 0)
        if item:
            pharmacie_id = item.data(Qt.ItemDataRole.UserRole)
            if pharmacie_id:
                self.pharmacie_selectionnee.emit(pharmacie_id)

    def _on_clic_cellule(self, row, col):
        if col != 10:  # Pas la colonne Actions
            item = self.tableau.item(row, 0)
            if item:
                pharmacie_id = item.data(Qt.ItemDataRole.UserRole)
                if pharmacie_id:
                    self.pharmacie_selectionnee.emit(pharmacie_id)

    def _enrichir_une(self):
        btn = self.sender()
        if not btn:
            return
        pharmacie_id = btn.property("pharmacie_id")
        if not pharmacie_id:
            return
        pharm = database.get_pharmacie(self.db_path, pharmacie_id)
        if not pharm:
            return

        from enricher import enrichir_pharmacie
        try:
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

        self.btn_enrichir_lot.setText("Arrêter l'enrichissement")
        self.barre_progress.setVisible(True)
        self.label_progress.setVisible(True)
        self.barre_progress.setValue(0)

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
            self,
            "Enrichissement terminé",
            f"Résultats :\n"
            f"• Enrichies : {compteurs.get('enrichies', 0)}\n"
            f"• Sans résultat : {compteurs.get('sans_resultat', 0)}\n"
            f"• Erreurs : {compteurs.get('erreurs', 0)}"
        )

    def _exporter(self):
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter", "", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not chemin:
            return

        pharmacies = database.lister_pharmacies(
            self.db_path,
            recherche=self.input_recherche.text().strip(),
            departement=self.combo_dept.currentData() or "",
            statut=self.combo_statut.currentData() or "",
            en_cible_only=self.check_cible.isChecked(),
            non_enrichies_only=self.check_non_enrichies.isChecked(),
        )

        try:
            if chemin.endswith(".csv"):
                _exporter_csv(pharmacies, chemin)
            else:
                _exporter_excel(pharmacies, chemin)
            QMessageBox.information(self, "Export réussi", f"Fichier enregistré :\n{chemin}")
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

    entetes = [
        "Nom", "Adresse", "Ville", "CP", "Département", "Téléphone", "Fax",
        "Email", "Nom décidant", "Prénom décidant", "Tél décidant", "Email décidant",
        "CA tranche", "CA estimé (€)", "En cible", "Statut", "Source", "Enrichi",
    ]
    ws.append(entetes)

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
        writer.writerow([
            "Nom", "Adresse", "Ville", "CP", "Département", "Téléphone",
            "Email", "CA tranche", "En cible", "Statut",
        ])
        for p in pharmacies:
            writer.writerow([
                p["nom"], p["adresse"], p["ville"], p["code_postal"],
                p["departement"], p["telephone"], p["email"],
                p["ca_tranche"], "Oui" if p["en_cible"] else "Non", p["statut"],
            ])
