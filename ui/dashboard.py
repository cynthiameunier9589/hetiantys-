"""
Tableau de bord : statistiques globales. Version sans PyQt6-Charts pour compatibilité Mac.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

import database


COULEURS_STATUTS = {
    "À contacter": "#90A4AE",
    "À rappeler": "#FFB300",
    "Mail envoyé": "#42A5F5",
    "RDV pris": "#AB47BC",
    "Borne posée": "#26A69A",
    "Pas intéressé": "#EF5350",
}


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return iso[:10]


class CarteKPI(QFrame):
    """Carte affichant un indicateur clé."""

    def __init__(self, titre: str, valeur: str, couleur: str = "#1565C0", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {couleur}; border-radius: 8px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self.lbl_val = QLabel(valeur)
        self.lbl_val.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        self.lbl_val.setStyleSheet("color: white; background: transparent;")
        layout.addWidget(self.lbl_val)

        lbl_titre = QLabel(titre)
        lbl_titre.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px; background: transparent;")
        layout.addWidget(lbl_titre)

    def set_valeur(self, valeur: str):
        self.lbl_val.setText(valeur)


class BarreStatut(QWidget):
    """Barre horizontale simple pour représenter un statut."""

    def __init__(self, statut: str, nb: int, nb_max: int, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        lbl_statut = QLabel(statut)
        lbl_statut.setFixedWidth(140)
        lbl_statut.setStyleSheet("font-size: 12px; color: #333;")
        layout.addWidget(lbl_statut)

        # Barre de progression
        barre = QFrame()
        largeur = int((nb / nb_max) * 200) if nb_max > 0 else 0
        largeur = max(largeur, 4)
        couleur = COULEURS_STATUTS.get(statut, "#90A4AE")
        barre.setFixedSize(largeur, 18)
        barre.setStyleSheet(f"background: {couleur}; border-radius: 3px;")
        layout.addWidget(barre)

        lbl_nb = QLabel(str(nb))
        lbl_nb.setStyleSheet("font-size: 12px; font-weight: bold; color: #333;")
        layout.addWidget(lbl_nb)
        layout.addStretch()


class Dashboard(QWidget):
    """Page tableau de bord."""

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._construire_ui()

    def _construire_ui(self):
        layout_root = QVBoxLayout(self)
        layout_root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        contenu = QWidget()
        layout = QVBoxLayout(contenu)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Titre
        titre = QLabel("Tableau de bord")
        titre.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(titre)

        # ── Ligne KPI ──
        ligne_kpi = QHBoxLayout()
        ligne_kpi.setSpacing(12)

        self.kpi_total = CarteKPI("Total pharmacies", "0", "#1565C0")
        self.kpi_cible = CarteKPI("En cible", "0", "#2e7d32")
        self.kpi_hors_cible = CarteKPI("Hors cible", "0", "#757575")
        self.kpi_non_contactees = CarteKPI("Non contactées", "0", "#e65100")

        for kpi in (self.kpi_total, self.kpi_cible, self.kpi_hors_cible, self.kpi_non_contactees):
            ligne_kpi.addWidget(kpi)

        layout.addLayout(ligne_kpi)

        # ── Graphique par statut + Top départements ──
        ligne_graphiques = QHBoxLayout()
        ligne_graphiques.setSpacing(16)

        # Répartition par statut (barres simples)
        grp_statuts = QFrame()
        grp_statuts.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 6px; padding: 4px; }")
        statuts_layout = QVBoxLayout(grp_statuts)
        statuts_layout.setContentsMargins(12, 12, 12, 12)
        lbl_statuts = QLabel("Répartition par statut")
        lbl_statuts.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        lbl_statuts.setStyleSheet("border: none;")
        statuts_layout.addWidget(lbl_statuts)
        self.container_statuts = QVBoxLayout()
        statuts_layout.addLayout(self.container_statuts)
        statuts_layout.addStretch()
        ligne_graphiques.addWidget(grp_statuts, 3)

        # Top départements
        grp_depts = QFrame()
        grp_depts.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 6px; padding: 4px; }")
        depts_layout = QVBoxLayout(grp_depts)
        depts_layout.setContentsMargins(12, 12, 12, 12)
        lbl_depts = QLabel("Top 5 départements (en cible)")
        lbl_depts.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        lbl_depts.setStyleSheet("border: none;")
        depts_layout.addWidget(lbl_depts)
        self.container_depts = QVBoxLayout()
        depts_layout.addLayout(self.container_depts)
        depts_layout.addStretch()
        ligne_graphiques.addWidget(grp_depts, 2)

        layout.addLayout(ligne_graphiques)

        # ── Dernières modifications ──
        grp_recents = QFrame()
        grp_recents.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 6px; padding: 4px; }")
        recents_layout = QVBoxLayout(grp_recents)
        recents_layout.setContentsMargins(12, 12, 12, 12)
        lbl_recents = QLabel("Dernières pharmacies modifiées")
        lbl_recents.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        lbl_recents.setStyleSheet("border: none;")
        recents_layout.addWidget(lbl_recents)
        self.container_recents = QVBoxLayout()
        self.container_recents.setSpacing(2)
        recents_layout.addLayout(self.container_recents)
        layout.addWidget(grp_recents)

        layout.addStretch()

        scroll.setWidget(contenu)
        layout_root.addWidget(scroll)

    def actualiser(self):
        """Recharge toutes les statistiques depuis la base."""
        try:
            stats = database.get_statistiques(self.db_path)
        except Exception:
            return

        self.kpi_total.set_valeur(str(stats["total"]))
        self.kpi_cible.set_valeur(str(stats["en_cible"]))
        self.kpi_hors_cible.set_valeur(str(stats["hors_cible"]))
        self.kpi_non_contactees.set_valeur(str(stats["non_contactees"]))

        # Barres par statut
        self._vider_layout(self.container_statuts)
        par_statut = stats["par_statut"]
        nb_max = max((nb for _, nb in par_statut), default=1)
        for statut, nb in par_statut:
            self.container_statuts.addWidget(BarreStatut(statut, nb, nb_max))

        # Top départements
        self._vider_layout(self.container_depts)
        medailles = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, (dept, nb) in enumerate(stats["top_departements"]):
            ligne = QHBoxLayout()
            medaille = medailles[i] if i < 5 else f"{i+1}."
            lbl = QLabel(f"{medaille}  Département {dept}")
            lbl.setStyleSheet("font-size: 13px;")
            ligne.addWidget(lbl)
            ligne.addStretch()
            lbl_nb = QLabel(f"{nb} en cible")
            lbl_nb.setStyleSheet("color: #2e7d32; font-size: 13px; font-weight: bold;")
            ligne.addWidget(lbl_nb)
            self.container_depts.addLayout(ligne)

        # Dernières modifications
        self._vider_layout(self.container_recents)
        en_tete = QHBoxLayout()
        for col, stretch in [("Nom", 3), ("Ville", 2), ("Statut", 2), ("Dernière modif.", 2)]:
            lbl = QLabel(col)
            lbl.setStyleSheet("font-weight: bold; color: #555; font-size: 11px;")
            en_tete.addWidget(lbl, stretch)
        self.container_recents.addLayout(en_tete)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #eee;")
        self.container_recents.addWidget(sep)

        for pharm in stats["dernieres_modifications"]:
            ligne = QHBoxLayout()
            nom_lbl = QLabel(pharm["nom"] or "")
            nom_lbl.setStyleSheet("font-size: 12px;")
            ligne.addWidget(nom_lbl, 3)
            ville_lbl = QLabel(pharm["ville"] or "")
            ville_lbl.setStyleSheet("font-size: 12px; color: #555;")
            ligne.addWidget(ville_lbl, 2)
            couleur = COULEURS_STATUTS.get(pharm["statut"], "#888")
            statut_lbl = QLabel(pharm["statut"] or "")
            statut_lbl.setStyleSheet(f"font-size: 11px; color: {couleur}; font-weight: bold;")
            ligne.addWidget(statut_lbl, 2)
            date_lbl = QLabel(_fmt_date(pharm["date_modification"] or ""))
            date_lbl.setStyleSheet("font-size: 11px; color: #888;")
            ligne.addWidget(date_lbl, 2)
            self.container_recents.addLayout(ligne)

    def _vider_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._vider_layout(item.layout())

    def set_db_path(self, db_path: str):
        self.db_path = db_path
        self.actualiser()
