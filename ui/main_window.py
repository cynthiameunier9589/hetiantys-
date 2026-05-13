"""
Fenêtre principale de l'application Heliantys.
Navigation latérale avec 4 sections : Tableau de bord, Pharmacies, Scraping, Paramètres.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor

from ui.dashboard import Dashboard
from ui.pharmacie_list import ListePharmacies
from ui.pharmacie_detail import FichePharmacieDetail
from ui.scraping_dialog import ScrapingDialog
from ui.settings import PageParametres


STYLE_SIDEBAR = """
QFrame#sidebar {
    background-color: #1a237e;
    border-right: 1px solid #0d1b6e;
}
"""

STYLE_BTN_NAV = """
QPushButton {
    color: rgba(255,255,255,0.75);
    background: transparent;
    border: none;
    text-align: left;
    padding: 12px 16px;
    font-size: 13px;
    border-radius: 0;
}
QPushButton:hover {
    background: rgba(255,255,255,0.1);
    color: white;
}
QPushButton[actif="true"] {
    background: rgba(255,255,255,0.15);
    color: white;
    font-weight: bold;
    border-left: 3px solid #64B5F6;
}
"""


class MainWindow(QMainWindow):
    """Fenêtre principale avec navigation latérale."""

    def __init__(self, config: dict, config_path: str):
        super().__init__()
        self.config = config
        self.config_path = config_path

        self.setWindowTitle("Heliantys — Gestion de la prospection")
        self.setMinimumSize(1280, 800)

        self._construire_ui()
        self._actualiser_tableau_de_bord()

    def _construire_ui(self):
        widget_central = QWidget()
        self.setCentralWidget(widget_central)
        layout_principal = QHBoxLayout(widget_central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ── Barre latérale ──
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet(STYLE_SIDEBAR)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo / titre
        entete_sidebar = QFrame()
        entete_sidebar.setStyleSheet("background: #0d1b6e; padding: 0;")
        entete_sidebar.setFixedHeight(70)
        entete_layout = QVBoxLayout(entete_sidebar)
        entete_layout.setContentsMargins(16, 12, 16, 12)

        lbl_app = QLabel("Heliantys")
        lbl_app.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        lbl_app.setStyleSheet("color: white;")
        entete_layout.addWidget(lbl_app)

        lbl_sous = QLabel("Gestion Prospection")
        lbl_sous.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        entete_layout.addWidget(lbl_sous)

        sidebar_layout.addWidget(entete_sidebar)

        # Prénom utilisateur
        self.lbl_utilisateur = QLabel(f"👤 {self.config.get('prenom', '')}")
        self.lbl_utilisateur.setStyleSheet(
            "color: rgba(255,255,255,0.6); font-size: 11px; padding: 8px 16px;"
        )
        sidebar_layout.addWidget(self.lbl_utilisateur)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,0.1);")
        sidebar_layout.addWidget(sep)

        # Boutons navigation
        self._btns_nav = {}
        nav_items = [
            ("dashboard", "📊  Tableau de bord"),
            ("pharmacies", "💊  Pharmacies"),
            ("parametres", "⚙️  Paramètres"),
        ]

        for cle, label in nav_items:
            btn = QPushButton(label)
            btn.setStyleSheet(STYLE_NAV := STYLE_BTN_NAV)
            btn.setMinimumHeight(46)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setProperty("actif", False)
            btn.clicked.connect(lambda checked, c=cle: self._naviguer(c))
            self._btns_nav[cle] = btn
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Version en bas
        lbl_version = QLabel("v1.0.0")
        lbl_version.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px; padding: 8px 16px;")
        sidebar_layout.addWidget(lbl_version)

        layout_principal.addWidget(self.sidebar)

        # ── Zone de contenu ──
        self.stack = QStackedWidget()
        layout_principal.addWidget(self.stack)

        db_path = self.config.get("chemin_db", "")
        token = self.config.get("token_pappers", "")
        prenom = self.config.get("prenom", "")

        # Pages
        self.page_dashboard = Dashboard(db_path)
        self.stack.addWidget(self.page_dashboard)  # index 0

        self.page_liste = ListePharmacies(db_path, token)
        self.page_liste.pharmacie_selectionnee.connect(self._ouvrir_fiche)
        self.page_liste.btn_scraper.clicked.connect(self._ouvrir_scraping)
        self.stack.addWidget(self.page_liste)  # index 1

        self.page_fiche = FichePharmacieDetail(db_path, prenom)
        self.page_fiche.retour_liste.connect(lambda: self._naviguer("pharmacies"))
        self.stack.addWidget(self.page_fiche)  # index 2

        self.page_parametres = PageParametres(self.config_path, self.config)
        self.page_parametres.config_modifiee.connect(self._on_config_modifiee)
        self.stack.addWidget(self.page_parametres)  # index 3

        # Délai pour laisser la fenêtre s'afficher avant de charger les données
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, lambda: self._naviguer("dashboard"))

    def _naviguer(self, cle: str):
        """Navigue vers une section de l'application."""
        mapping = {
            "dashboard": 0,
            "pharmacies": 1,
            "fiche": 2,
            "parametres": 3,
        }

        index = mapping.get(cle, 0)
        self.stack.setCurrentIndex(index)

        # Mise à jour visuelle des boutons
        for k, btn in self._btns_nav.items():
            actif = k == cle or (cle == "fiche" and k == "pharmacies")
            btn.setProperty("actif", str(actif).lower())
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Actualisation selon la page
        if cle == "dashboard":
            self._actualiser_tableau_de_bord()
        elif cle == "pharmacies":
            self.page_liste.actualiser()

    def _ouvrir_fiche(self, pharmacie_id: int):
        """Ouvre la fiche détaillée d'une pharmacie."""
        self.page_fiche.charger_pharmacie(pharmacie_id)
        self.stack.setCurrentIndex(2)

        for k, btn in self._btns_nav.items():
            actif = k == "pharmacies"
            btn.setProperty("actif", str(actif).lower())
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _ouvrir_scraping(self):
        """Ouvre la boîte de dialogue de scraping."""
        db_path = self.config.get("chemin_db", "")
        dialog = ScrapingDialog(db_path, parent=self)
        dialog.exec()
        self.page_liste.actualiser()

    def _actualiser_tableau_de_bord(self):
        db_path = self.config.get("chemin_db", "")
        self.page_dashboard.set_db_path(db_path)

    def _on_config_modifiee(self, nouvelle_config: dict):
        """Met à jour l'application après un changement de configuration."""
        self.config = nouvelle_config
        db_path = nouvelle_config.get("chemin_db", "")
        prenom = nouvelle_config.get("prenom", "")
        token = nouvelle_config.get("token_pappers", "")

        self.lbl_utilisateur.setText(f"👤 {prenom}")
        self.page_liste.set_db_path(db_path)
        self.page_liste.set_api_token(token)
        self.page_fiche.set_db_path(db_path)
        self.page_fiche.set_prenom(prenom)
        self.page_dashboard.set_db_path(db_path)
