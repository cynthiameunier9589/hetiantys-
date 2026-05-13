"""
Assistant de premier lancement : collecte prénom, chemin DB et token Pappers.
Sauvegarde dans config.json local (non partagé).
"""

import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap


class SetupWizard(QDialog):
    """Fenêtre de configuration au premier lancement."""

    def __init__(self, config_path: str, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self.setWindowTitle("Configuration initiale — Heliantys")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._construire_ui()

    def _construire_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 32, 32, 32)

        # En-tête
        titre = QLabel("Bienvenue dans Heliantys Prospection")
        titre.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titre)

        sous_titre = QLabel("Configurez votre poste de travail pour commencer")
        sous_titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sous_titre.setStyleSheet("color: #666;")
        layout.addWidget(sous_titre)

        separateur = QFrame()
        separateur.setFrameShape(QFrame.Shape.HLine)
        separateur.setStyleSheet("color: #ddd;")
        layout.addWidget(separateur)

        # Champ prénom
        layout.addWidget(QLabel("Votre prénom * :"))
        self.input_prenom = QLineEdit()
        self.input_prenom.setPlaceholderText("ex : Jean")
        self.input_prenom.setMinimumHeight(36)
        layout.addWidget(self.input_prenom)

        hint_prenom = QLabel("Utilisé pour horodater vos notes et historiques d'activité.")
        hint_prenom.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint_prenom)

        # Champ chemin base de données
        layout.addWidget(QLabel("Chemin vers la base de données (.db) :"))
        ligne_db = QHBoxLayout()
        self.input_db = QLineEdit()
        self.input_db.setPlaceholderText("Laisser vide pour créer localement (heliantys.db)")
        self.input_db.setMinimumHeight(36)
        ligne_db.addWidget(self.input_db)
        btn_parcourir = QPushButton("Parcourir…")
        btn_parcourir.setFixedWidth(100)
        btn_parcourir.clicked.connect(self._choisir_chemin_db)
        ligne_db.addWidget(btn_parcourir)
        layout.addLayout(ligne_db)

        hint_db = QLabel(
            "Sur OneDrive partagé, pointez vers le même fichier .db que vos collègues.\n"
            "Exemple : C:/Users/Jean/OneDrive/Heliantys/heliantys.db"
        )
        hint_db.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint_db)

        # Champ token Pappers
        layout.addWidget(QLabel("Token API Pappers (optionnel) :"))
        self.input_token = QLineEdit()
        self.input_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_token.setPlaceholderText("Peut être renseigné plus tard dans les Paramètres")
        self.input_token.setMinimumHeight(36)
        layout.addWidget(self.input_token)

        hint_token = QLabel(
            "Clé API gratuite disponible sur pappers.fr — améliore la détection des dirigeants."
        )
        hint_token.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint_token)

        layout.addStretch()

        # Boutons
        ligne_boutons = QHBoxLayout()
        ligne_boutons.addStretch()
        self.btn_valider = QPushButton("Démarrer l'application")
        self.btn_valider.setMinimumHeight(40)
        self.btn_valider.setMinimumWidth(200)
        self.btn_valider.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1b5e20; }"
        )
        self.btn_valider.clicked.connect(self._valider)
        ligne_boutons.addWidget(self.btn_valider)
        layout.addLayout(ligne_boutons)

    def _choisir_chemin_db(self):
        chemin, _ = QFileDialog.getSaveFileName(
            self,
            "Choisir l'emplacement de la base de données",
            os.path.expanduser("~"),
            "Base SQLite (*.db)",
        )
        if chemin:
            if not chemin.endswith(".db"):
                chemin += ".db"
            self.input_db.setText(chemin)

    def _valider(self):
        prenom = self.input_prenom.text().strip()
        if not prenom:
            QMessageBox.warning(self, "Champ requis", "Veuillez saisir votre prénom.")
            self.input_prenom.setFocus()
            return

        chemin_db = self.input_db.text().strip()
        if not chemin_db:
            chemin_db = os.path.join(os.getcwd(), "heliantys.db")

        config = {
            "prenom": prenom,
            "chemin_db": chemin_db,
            "token_pappers": self.input_token.text().strip(),
        }

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder la configuration :\n{e}")
