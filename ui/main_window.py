"""
Fenêtre principale de l'application Heliantys.
Navigation latérale avec 4 sections : Tableau de bord, Pharmacies, Fiche, Paramètres.
Version compatible Mac/Python 3.9+
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ui.dashboard import Dashboard
from ui.pharmacie_list import ListePharmacies
from ui.pharmacie_detail import FichePharmacieDetail
from ui.scraping_dialog import ScrapingDialog
from ui.settings import PageParametres

# Styles fixes (pas de propriétés dynamiques — incompatibles Mac)
STYLE_BTN_INACTIF = (
    "QPushButton {"
    "  color: rgba(255,255,255,180);"
    "  background-color: transparent;"
    "  border: none;"
    "  text-align: left;"
    "  padding: 12px 20px;"
    "  font-size: 13px;"
    "}"
)

STYLE_BTN_ACTIF = (
    "QPushButton {"
    "  color: white;"
    "  background-color: rgba(255,255,255,40);"
    "  border: none;"
    "  border-left: 3px solid #64B5F6;"
    "  text-align: left;"
    "  padding: 12px 17px;"
    "  font-size: 13px;"
    "  font-weight: bold;"
    "}"
)


class MainWindow(QMainWindow):
    """Fenêtre principale avec navigation latérale."""

    def __init__(self, config: dict, config_path: str):
        super().__init__()
        self.config = config
        self.config_path = config_path
        self._btns_nav = {}

        self.setWindowTitle("Heliantys — Gestion de la prospection")
        self.setMinimumSize(1280, 800)

        self._construire_ui()

        # Chargement différé pour laisser la fenêtre s'afficher en premier
        QTimer.singleShot(100, lambda: self._naviguer("dashboard"))

    def _construire_ui(self):
        widget_central = QWidget()
        self.setCentralWidget(widget_central)
        layout_principal = QHBoxLayout(widget_central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ── Barre latérale ──
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("QFrame { background-color: #1a237e; }")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # En-tête
        entete = QFrame()
        entete.setStyleSheet("QFrame { background-color: #0d1b6e; }")
        entete.setFixedHeight(70)
        entete_layout = QVBoxLayout(entete)
        entete_layout.setContentsMargins(16, 12, 16, 12)

        lbl_app = QLabel("Heliantys")
        lbl_app.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        lbl_app.setStyleSheet("color: white; background: transparent;")
        entete_layout.addWidget(lbl_app)

        lbl_sous = QLabel("Gestion Prospection")
        lbl_sous.setStyleSheet("color: rgba(255,255,255,150); font-size: 11px; background: transparent;")
        entete_layout.addWidget(lbl_sous)

        sidebar_layout.addWidget(entete)

        # Nom utilisateur
        self.lbl_utilisateur = QLabel(f"  {self.config.get('prenom', '')}")
        self.lbl_utilisateur.setStyleSheet(
            "color: rgba(255,255,255,150); font-size: 12px; padding: 8px 16px; background: transparent;"
        )
        sidebar_layout.addWidget(self.lbl_utilisateur)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("border: none; background-color: rgba(255,255,255,30); max-height: 1px;")
        sep.setFixedHeight(1)
        sidebar_layout.addWidget(sep)

        # Boutons navigation
        nav_items = [
            ("dashboard", "Tableau de bord"),
            ("pharmacies", "Pharmacies"),
            ("parametres", "Parametres"),
        ]

        for cle, label in nav_items:
            btn = QPushButton(label)
            btn.setStyleSheet(STYLE_BTN_INACTIF)
            btn.setMinimumHeight(48)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=cle: self._naviguer(c))
            self._btns_nav[cle] = btn
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        lbl_version = QLabel("v1.0.0")
        lbl_version.setStyleSheet("color: rgba(255,255,255,60); font-size: 10px; padding: 8px 16px; background: transparent;")
        sidebar_layout.addWidget(lbl_version)

        layout_principal.addWidget(sidebar)

        # ── Zone de contenu ──
        self.stack = QStackedWidget()
        layout_principal.addWidget(self.stack)

        db_path = self.config.get("chemin_db", "")
        token = self.config.get("token_pappers", "")
        prenom = self.config.get("prenom", "")

        self.page_dashboard = Dashboard(db_path)
        self.stack.addWidget(self.page_dashboard)      # index 0

        self.page_liste = ListePharmacies(db_path, token)
        self.page_liste.pharmacie_selectionnee.connect(self._ouvrir_fiche)
        self.page_liste.btn_scraper.clicked.connect(self._ouvrir_scraping)
        self.stack.addWidget(self.page_liste)          # index 1

        self.page_fiche = FichePharmacieDetail(db_path, prenom)
        self.page_fiche.retour_liste.connect(lambda: self._naviguer("pharmacies"))
        self.stack.addWidget(self.page_fiche)          # index 2

        self.page_parametres = PageParametres(self.config_path, self.config)
        self.page_parametres.config_modifiee.connect(self._on_config_modifiee)
        self.stack.addWidget(self.page_parametres)     # index 3

    def _naviguer(self, cle: str):
        """Navigue vers une section et met à jour la surbrillance des boutons."""
        mapping = {"dashboard": 0, "pharmacies": 1, "fiche": 2, "parametres": 3}
        index = mapping.get(cle, 0)
        self.stack.setCurrentIndex(index)

        # Surbrillance simple sans unpolish/polish
        for k, btn in self._btns_nav.items():
            actif = (k == cle) or (cle == "fiche" and k == "pharmacies")
            btn.setStyleSheet(STYLE_BTN_ACTIF if actif else STYLE_BTN_INACTIF)

        if cle == "dashboard":
            try:
                self.page_dashboard.actualiser()
            except Exception:
                pass
        elif cle == "pharmacies":
            try:
                self.page_liste.actualiser()
            except Exception:
                pass

    def _ouvrir_fiche(self, pharmacie_id: int):
        self.page_fiche.charger_pharmacie(pharmacie_id)
        self.stack.setCurrentIndex(2)
        for k, btn in self._btns_nav.items():
            btn.setStyleSheet(STYLE_BTN_ACTIF if k == "pharmacies" else STYLE_BTN_INACTIF)

    def _ouvrir_scraping(self):
        db_path = self.config.get("chemin_db", "")
        dialog = ScrapingDialog(db_path, parent=self)
        dialog.exec()
        # Naviguer vers la liste et la rafraîchir pour afficher les nouvelles pharmacies
        self._naviguer("pharmacies")

    def _on_config_modifiee(self, nouvelle_config: dict):
        self.config = nouvelle_config
        db_path = nouvelle_config.get("chemin_db", "")
        prenom = nouvelle_config.get("prenom", "")
        token = nouvelle_config.get("token_pappers", "")

        self.lbl_utilisateur.setText(f"  {prenom}")
        self.page_liste.set_db_path(db_path)
        self.page_liste.set_api_token(token)
        self.page_fiche.set_db_path(db_path)
        self.page_fiche.set_prenom(prenom)
        self.page_dashboard.set_db_path(db_path)
