"""
Tableau de bord : statistiques globales et graphiques de répartition.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PyQt6.QtCharts import QChart, QChartView, QBarSet, QHorizontalBarSeries, QBarCategoryAxis, QValueAxis

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
            f"QFrame {{ background: {couleur}; border-radius: 8px; padding: 8px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        lbl_val = QLabel(valeur)
        lbl_val.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        lbl_val.setStyleSheet("color: white;")
        layout.addWidget(lbl_val)

        lbl_titre = QLabel(titre)
        lbl_titre.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px;")
        layout.addWidget(lbl_titre)

    def set_valeur(self, valeur: str):
        self.findChild(QLabel).setText(valeur)


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
        self.grille_kpi = QHBoxLayout()
        self.kpi_total = CarteKPI("Total pharmacies", "0", "#1565C0")
        self.kpi_cible = CarteKPI("En cible", "0", "#2e7d32")
        self.kpi_hors_cible = CarteKPI("Hors cible", "0", "#757575")
        self.kpi_non_contactees = CarteKPI("Non contactées", "0", "#e65100")

        for kpi in (self.kpi_total, self.kpi_cible, self.kpi_hors_cible, self.kpi_non_contactees):
            self.grille_kpi.addWidget(kpi)

        layout.addLayout(self.grille_kpi)

        # ── Graphique par statut + Top départements ──
        ligne_graphiques = QHBoxLayout()
        ligne_graphiques.setSpacing(16)

        # Graphique statuts
        grp_statuts = QFrame()
        grp_statuts.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 6px; padding: 8px; }")
        statuts_layout = QVBoxLayout(grp_statuts)
        lbl_statuts = QLabel("Répartition par statut")
        lbl_statuts.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        statuts_layout.addWidget(lbl_statuts)
        self.vue_graphique = QChartView()
        self.vue_graphique.setMinimumHeight(250)
        self.vue_graphique.setRenderHint(QPainter.RenderHint.Antialiasing)
        statuts_layout.addWidget(self.vue_graphique)
        ligne_graphiques.addWidget(grp_statuts, 3)

        # Top départements
        grp_depts = QFrame()
        grp_depts.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 6px; padding: 8px; }")
        depts_layout = QVBoxLayout(grp_depts)
        lbl_depts = QLabel("Top 5 départements (en cible)")
        lbl_depts.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        depts_layout.addWidget(lbl_depts)
        self.container_depts = QVBoxLayout()
        depts_layout.addLayout(self.container_depts)
        depts_layout.addStretch()
        ligne_graphiques.addWidget(grp_depts, 2)

        layout.addLayout(ligne_graphiques)

        # ── Dernières modifications ──
        grp_recents = QFrame()
        grp_recents.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 6px; padding: 8px; }")
        recents_layout = QVBoxLayout(grp_recents)
        lbl_recents = QLabel("Dernières pharmacies modifiées")
        lbl_recents.setFont(QFont("Arial", 12, QFont.Weight.Bold))
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
        stats = database.get_statistiques(self.db_path)

        # KPI
        self.kpi_total.findChildren(QLabel)[0].setText(str(stats["total"]))
        self.kpi_cible.findChildren(QLabel)[0].setText(str(stats["en_cible"]))
        self.kpi_hors_cible.findChildren(QLabel)[0].setText(str(stats["hors_cible"]))
        self.kpi_non_contactees.findChildren(QLabel)[0].setText(str(stats["non_contactees"]))

        # Graphique par statut
        self._construire_graphique_statuts(stats["par_statut"])

        # Top départements
        self._vider_layout(self.container_depts)
        for i, (dept, nb) in enumerate(stats["top_departements"]):
            ligne = QHBoxLayout()
            medaille = ["🥇", "🥈", "🥉", "4.", "5."][i] if i < 5 else f"{i+1}."
            lbl = QLabel(f"{medaille}  Dpt {dept}")
            lbl.setStyleSheet("font-size: 13px;")
            ligne.addWidget(lbl)
            ligne.addStretch()
            lbl_nb = QLabel(f"<b>{nb}</b> en cible")
            lbl_nb.setStyleSheet("color: #2e7d32; font-size: 13px;")
            ligne.addWidget(lbl_nb)
            self.container_depts.addLayout(ligne)

        # Dernières modifications
        self._vider_layout(self.container_recents)
        en_tete = QHBoxLayout()
        for col in ("Nom", "Ville", "Statut", "Dernière modif."):
            lbl = QLabel(col)
            lbl.setStyleSheet("font-weight: bold; color: #555; font-size: 11px;")
            en_tete.addWidget(lbl, 3 if col == "Nom" else 2)
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
            statut_lbl = QLabel(pharm["statut"] or "")
            couleur = COULEURS_STATUTS.get(pharm["statut"], "#888")
            statut_lbl.setStyleSheet(
                f"font-size: 11px; color: {couleur}; font-weight: bold;"
            )
            ligne.addWidget(statut_lbl, 2)
            date_lbl = QLabel(_fmt_date(pharm["date_modification"] or ""))
            date_lbl.setStyleSheet("font-size: 11px; color: #888;")
            ligne.addWidget(date_lbl, 2)
            self.container_recents.addLayout(ligne)

    def _construire_graphique_statuts(self, par_statut):
        """Construit le graphique horizontal par statut."""
        chart = QChart()
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        chart.legend().setVisible(False)
        chart.setBackgroundVisible(False)
        chart.setMargins(chart.margins().__class__(4, 4, 4, 4))

        categories = []
        serie = QHorizontalBarSeries()

        for statut, nb in par_statut:
            bar_set = QBarSet(statut)
            couleur = COULEURS_STATUTS.get(statut, "#90A4AE")
            bar_set.setColor(QColor(couleur))
            bar_set.append(nb)
            bar_set.setLabel(str(nb))
            serie.append(bar_set)
            categories.append(f"{statut} ({nb})")

        chart.addSeries(serie)

        axe_y = QBarCategoryAxis()
        axe_y.append(categories)
        chart.addAxis(axe_y, Qt.AlignmentFlag.AlignLeft)
        serie.attachAxis(axe_y)

        axe_x = QValueAxis()
        axe_x.setLabelFormat("%d")
        chart.addAxis(axe_x, Qt.AlignmentFlag.AlignBottom)
        serie.attachAxis(axe_x)

        chart.setTitle("")
        self.vue_graphique.setChart(chart)

    def _vider_layout(self, layout):
        """Vide récursivement un layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._vider_layout(item.layout())

    def set_db_path(self, db_path: str):
        self.db_path = db_path
        self.actualiser()
