"""
Page de paramètres : prénom, token Pappers, chemin DB, import/export.
"""

import json
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QFrame, QGroupBox,
    QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

import database


class PageParametres(QWidget):
    """Page de paramètres de l'application."""

    config_modifiee = pyqtSignal(dict)

    def __init__(self, config_path: str, config: dict, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self.config = dict(config)
        self._construire_ui()
        self._charger_config()

    def _construire_ui(self):
        layout_root = QVBoxLayout(self)
        layout_root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        contenu = QWidget()
        layout = QVBoxLayout(contenu)
        layout.setContentsMargins(32, 24, 32, 32)
        layout.setSpacing(20)

        titre = QLabel("Paramètres")
        titre.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(titre)

        # ── Profil utilisateur ──
        grp_profil = QGroupBox("Profil utilisateur")
        grp_profil.setStyleSheet(self._style_groupe())
        profil_layout = QVBoxLayout(grp_profil)

        profil_layout.addWidget(QLabel("Votre prénom :"))
        self.input_prenom = QLineEdit()
        self.input_prenom.setMinimumHeight(34)
        profil_layout.addWidget(self.input_prenom)

        hint = QLabel("Utilisé pour horodater les notes et historiques de statut.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        profil_layout.addWidget(hint)

        layout.addWidget(grp_profil)

        # ── Base de données ──
        grp_db = QGroupBox("Base de données")
        grp_db.setStyleSheet(self._style_groupe())
        db_layout = QVBoxLayout(grp_db)

        db_layout.addWidget(QLabel("Chemin vers le fichier SQLite (.db) :"))
        ligne_db = QHBoxLayout()
        self.input_chemin_db = QLineEdit()
        self.input_chemin_db.setMinimumHeight(34)
        ligne_db.addWidget(self.input_chemin_db)
        btn_parcourir = QPushButton("Parcourir…")
        btn_parcourir.clicked.connect(self._choisir_db)
        ligne_db.addWidget(btn_parcourir)
        db_layout.addLayout(ligne_db)

        hint_db = QLabel(
            "Sur OneDrive partagé, tous les membres de l'équipe doivent pointer vers le même fichier."
        )
        hint_db.setStyleSheet("color: #888; font-size: 11px;")
        hint_db.setWordWrap(True)
        db_layout.addWidget(hint_db)

        self.btn_tester_db = QPushButton("Tester la connexion à la base")
        self.btn_tester_db.setStyleSheet(
            "QPushButton { background: #37474F; color: white; border-radius: 4px; padding: 6px 16px; }"
        )
        self.btn_tester_db.clicked.connect(self._tester_connexion)
        db_layout.addWidget(self.btn_tester_db)

        layout.addWidget(grp_db)

        # ── API Pappers ──
        grp_pappers = QGroupBox("API Pappers")
        grp_pappers.setStyleSheet(self._style_groupe())
        pappers_layout = QVBoxLayout(grp_pappers)

        pappers_layout.addWidget(QLabel("Token API Pappers :"))
        self.input_token = QLineEdit()
        self.input_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_token.setMinimumHeight(34)
        self.input_token.setPlaceholderText("Votre token (disponible sur pappers.fr)")
        pappers_layout.addWidget(self.input_token)

        hint_pappers = QLabel(
            "Le token est stocké localement sur ce poste uniquement (non partagé)."
        )
        hint_pappers.setStyleSheet("color: #888; font-size: 11px;")
        pappers_layout.addWidget(hint_pappers)

        layout.addWidget(grp_pappers)

        # ── Import / Export ──
        grp_import = QGroupBox("Import / Export")
        grp_import.setStyleSheet(self._style_groupe())
        import_layout = QVBoxLayout(grp_import)

        ligne_import = QHBoxLayout()
        self.btn_reimporter = QPushButton("Réimporter le fichier Excel")
        self.btn_reimporter.setStyleSheet(
            "QPushButton { background: #E65100; color: white; border-radius: 4px; padding: 8px 16px; }"
            "QPushButton:hover { background: #BF360C; }"
        )
        self.btn_reimporter.clicked.connect(self._reimporter_excel)
        ligne_import.addWidget(self.btn_reimporter)

        self.btn_exporter_tout = QPushButton("Exporter toute la base en Excel")
        self.btn_exporter_tout.setStyleSheet(
            "QPushButton { background: #2e7d32; color: white; border-radius: 4px; padding: 8px 16px; }"
            "QPushButton:hover { background: #1b5e20; }"
        )
        self.btn_exporter_tout.clicked.connect(self._exporter_tout)
        ligne_import.addWidget(self.btn_exporter_tout)
        ligne_import.addStretch()
        import_layout.addLayout(ligne_import)

        hint_import = QLabel(
            "La réimportation ne crée pas de doublons — seules les nouvelles pharmacies sont ajoutées."
        )
        hint_import.setStyleSheet("color: #888; font-size: 11px;")
        import_layout.addWidget(hint_import)

        layout.addWidget(grp_import)

        # ── Zone danger ──
        grp_danger = QGroupBox("Zone danger")
        grp_danger.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #ef9a9a; border-radius: 6px; "
            "margin-top: 8px; padding-top: 8px; color: #c62828; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        danger_layout = QVBoxLayout(grp_danger)

        self.btn_vider_base = QPushButton("Vider toute la base de données")
        self.btn_vider_base.setStyleSheet(
            "QPushButton { background: #c62828; color: white; border-radius: 4px; padding: 8px 16px; }"
            "QPushButton:pressed { background: #b71c1c; }"
        )
        self.btn_vider_base.clicked.connect(self._vider_base)
        danger_layout.addWidget(self.btn_vider_base)

        hint_danger = QLabel("Supprime toutes les fiches, notes et historiques. Irréversible.")
        hint_danger.setStyleSheet("color: #c62828; font-size: 11px;")
        danger_layout.addWidget(hint_danger)

        layout.addWidget(grp_danger)

        # Bouton sauvegarder
        layout.addStretch()
        self.btn_sauvegarder = QPushButton("Sauvegarder les paramètres")
        self.btn_sauvegarder.setMinimumHeight(40)
        self.btn_sauvegarder.setStyleSheet(
            "QPushButton { background: #1565C0; color: white; border-radius: 4px; font-weight: bold; padding: 0 24px; }"
            "QPushButton:hover { background: #0D47A1; }"
        )
        self.btn_sauvegarder.clicked.connect(self._sauvegarder)
        layout.addWidget(self.btn_sauvegarder, alignment=Qt.AlignmentFlag.AlignRight)

        scroll.setWidget(contenu)
        layout_root.addWidget(scroll)

    def _style_groupe(self) -> str:
        return (
            "QGroupBox { font-weight: bold; border: 1px solid #ddd; border-radius: 6px; "
            "margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )

    def _charger_config(self):
        self.input_prenom.setText(self.config.get("prenom", ""))
        self.input_chemin_db.setText(self.config.get("chemin_db", ""))
        self.input_token.setText(self.config.get("token_pappers", ""))

    def _choisir_db(self):
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Choisir la base de données", "", "SQLite (*.db)"
        )
        if chemin:
            if not chemin.endswith(".db"):
                chemin += ".db"
            self.input_chemin_db.setText(chemin)

    def _tester_connexion(self):
        chemin = self.input_chemin_db.text().strip()
        if not chemin:
            QMessageBox.warning(self, "Chemin manquant", "Veuillez saisir un chemin de base de données.")
            return
        try:
            database.initialiser_base(chemin)
            total = len(database.lister_pharmacies(chemin))
            QMessageBox.information(
                self,
                "Connexion réussie",
                f"Base accessible.\n{total} pharmacie(s) dans la base."
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur de connexion", str(e))

    def _reimporter_excel(self):
        chemin_excel, _ = QFileDialog.getOpenFileName(
            self, "Choisir le fichier Excel", "", "Excel (*.xlsx *.xls)"
        )
        if not chemin_excel:
            return

        rep = QMessageBox.question(
            self,
            "Confirmer la réimportation",
            "Voulez-vous réimporter ce fichier ?\n"
            "Les pharmacies déjà présentes ne seront pas dupliquées.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if rep != QMessageBox.StandardButton.Yes:
            return

        chemin_db = self.input_chemin_db.text().strip() or self.config.get("chemin_db", "")
        if not chemin_db:
            QMessageBox.warning(self, "Base manquante", "Configurez d'abord un chemin de base de données.")
            return

        try:
            from importer import importer_excel
            compteurs = importer_excel(chemin_db, chemin_excel)
            QMessageBox.information(
                self,
                "Import terminé",
                f"Résultats :\n"
                f"• Insérées : {compteurs['inserees']}\n"
                f"• Doublons ignorés : {compteurs['doublons']}\n"
                f"• Erreurs : {compteurs['erreurs']}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'import", str(e))

    def _exporter_tout(self):
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter toute la base", "", "Excel (*.xlsx)"
        )
        if not chemin:
            return

        chemin_db = self.input_chemin_db.text().strip() or self.config.get("chemin_db", "")
        try:
            pharmacies = database.lister_pharmacies(chemin_db)
            from ui.pharmacie_list import exporter_excel
            exporter_excel(pharmacies, chemin)
            QMessageBox.information(
                self, "Export réussi",
                f"{len(pharmacies)} pharmacies exportées vers :\n{chemin}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))

    def _vider_base(self):
        chemin_db = self.input_chemin_db.text().strip() or self.config.get("chemin_db", "")
        if not chemin_db:
            QMessageBox.warning(self, "Base manquante", "Configurez d'abord un chemin de base de données.")
            return
        rep = QMessageBox.question(
            self,
            "Confirmer la suppression",
            "Êtes-vous sûr de vouloir supprimer TOUTES les fiches ?\nCette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if rep != QMessageBox.StandardButton.Yes:
            return
        try:
            nb = database.vider_base(chemin_db)
            QMessageBox.information(self, "Base vidée", f"{nb} fiche(s) supprimée(s).")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def _sauvegarder(self):
        prenom = self.input_prenom.text().strip()
        if not prenom:
            QMessageBox.warning(self, "Champ requis", "Le prénom est obligatoire.")
            return

        self.config["prenom"] = prenom
        self.config["chemin_db"] = self.input_chemin_db.text().strip()
        self.config["token_pappers"] = self.input_token.text().strip()

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            self.config_modifiee.emit(dict(self.config))
            QMessageBox.information(self, "Paramètres sauvegardés", "Configuration enregistrée avec succès.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder :\n{e}")
