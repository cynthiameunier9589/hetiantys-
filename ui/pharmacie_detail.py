"""
Fiche détaillée d'une pharmacie : informations, décidant, suivi commercial, notes.
Toutes les sauvegardes sont automatiques (pas de bouton Enregistrer).
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTextEdit, QScrollArea, QFrame, QGroupBox, QSizePolicy,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

import database
from database import STATUTS_DISPONIBLES


def _fmt_date(iso: str) -> str:
    """Formatte une date ISO en format lisible."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m/%Y %Hh%M")
    except Exception:
        return iso[:16]


class ChampEditable(QWidget):
    """Label + LineEdit en lecture/écriture auto-sauvegardé."""

    valeur_changee = pyqtSignal(str, str)  # nom_champ, nouvelle_valeur

    def __init__(self, label: str, nom_champ: str, parent=None):
        super().__init__(parent)
        self.nom_champ = nom_champ
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._sauvegarder)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label)
        lbl.setFixedWidth(160)
        lbl.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(lbl)

        self.input = QLineEdit()
        self.input.setMinimumHeight(30)
        self.input.setStyleSheet(
            "QLineEdit { border: 1px solid #ddd; border-radius: 3px; padding: 2px 6px; }"
            "QLineEdit:focus { border-color: #1565C0; }"
        )
        self.input.textChanged.connect(lambda: self._timer.start(800))
        layout.addWidget(self.input)

    def set_valeur(self, valeur: str):
        self.input.blockSignals(True)
        self.input.setText(valeur or "")
        self.input.blockSignals(False)

    def get_valeur(self) -> str:
        return self.input.text().strip()

    def _sauvegarder(self):
        self.valeur_changee.emit(self.nom_champ, self.get_valeur())


class FichePharmacieDetail(QWidget):
    """Fiche détaillée complète d'une pharmacie."""

    retour_liste = pyqtSignal()

    def __init__(self, db_path: str, prenom_utilisateur: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.prenom_utilisateur = prenom_utilisateur
        self.pharmacie_id: int = 0
        self._suppression_statut_en_cours = False
        self._construire_ui()

    def _construire_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ── Barre de navigation ──
        barre_nav = QFrame()
        barre_nav.setStyleSheet("QFrame { background: #f5f5f5; border-bottom: 1px solid #ddd; }")
        barre_nav.setMaximumHeight(50)
        nav_layout = QHBoxLayout(barre_nav)
        nav_layout.setContentsMargins(16, 8, 16, 8)

        btn_retour = QPushButton("← Retour à la liste")
        btn_retour.setStyleSheet(
            "QPushButton { background: transparent; color: #1565C0; border: none; font-size: 13px; }"
            "QPushButton:hover { text-decoration: underline; }"
        )
        btn_retour.clicked.connect(self.retour_liste)
        nav_layout.addWidget(btn_retour)
        nav_layout.addStretch()

        self.label_titre_nav = QLabel("")
        self.label_titre_nav.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        nav_layout.addWidget(self.label_titre_nav)

        layout_principal.addWidget(barre_nav)

        # ── Contenu scrollable ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        contenu = QWidget()
        contenu_layout = QVBoxLayout(contenu)
        contenu_layout.setContentsMargins(24, 24, 24, 24)
        contenu_layout.setSpacing(16)

        # ── Section Pharmacie ──
        grp_pharmacie = QGroupBox("Informations Pharmacie")
        grp_pharmacie.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #ddd; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        pharmacie_layout = QVBoxLayout(grp_pharmacie)

        # Badge en cible / hors cible
        self.badge_cible = QLabel("")
        self.badge_cible.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.badge_cible.setFixedHeight(28)
        pharmacie_layout.addWidget(self.badge_cible)

        self.champ_nom = ChampEditable("Nom :", "nom")
        self.champ_nom.valeur_changee.connect(self._on_champ_change)
        pharmacie_layout.addWidget(self.champ_nom)

        self.champ_adresse = ChampEditable("Adresse :", "adresse")
        self.champ_adresse.valeur_changee.connect(self._on_champ_change)
        pharmacie_layout.addWidget(self.champ_adresse)

        ligne_geo = QHBoxLayout()
        self.champ_ville = ChampEditable("Ville :", "ville")
        self.champ_ville.valeur_changee.connect(self._on_champ_change)
        ligne_geo.addWidget(self.champ_ville)
        self.champ_cp = ChampEditable("Code postal :", "code_postal")
        self.champ_cp.valeur_changee.connect(self._on_champ_change)
        ligne_geo.addWidget(self.champ_cp)
        self.champ_dept = ChampEditable("Département :", "departement")
        self.champ_dept.valeur_changee.connect(self._on_champ_change)
        ligne_geo.addWidget(self.champ_dept)
        pharmacie_layout.addLayout(ligne_geo)

        ligne_contact = QHBoxLayout()
        self.champ_tel = ChampEditable("Téléphone :", "telephone")
        self.champ_tel.valeur_changee.connect(self._on_champ_change)
        ligne_contact.addWidget(self.champ_tel)
        self.champ_fax = ChampEditable("Fax :", "fax")
        self.champ_fax.valeur_changee.connect(self._on_champ_change)
        ligne_contact.addWidget(self.champ_fax)
        pharmacie_layout.addLayout(ligne_contact)

        self.champ_email = ChampEditable("Email général :", "email")
        self.champ_email.valeur_changee.connect(self._on_champ_change)
        pharmacie_layout.addWidget(self.champ_email)

        ligne_ca = QHBoxLayout()
        self.champ_ca_tranche = ChampEditable("CA tranche :", "ca_tranche")
        self.champ_ca_tranche.valeur_changee.connect(self._on_champ_change)
        ligne_ca.addWidget(self.champ_ca_tranche)
        self.label_ca_value = QLabel("")
        self.label_ca_value.setStyleSheet("color: #555; font-size: 12px;")
        ligne_ca.addWidget(self.label_ca_value)
        ligne_ca.addStretch()
        pharmacie_layout.addLayout(ligne_ca)

        self.label_source = QLabel("")
        self.label_source.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        pharmacie_layout.addWidget(self.label_source)

        contenu_layout.addWidget(grp_pharmacie)

        # ── Section Décidant ──
        grp_decidant = QGroupBox("Pharmacien titulaire / Propriétaire")
        grp_decidant.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #ddd; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        decidant_layout = QVBoxLayout(grp_decidant)

        hint_decidant = QLabel(
            "Le décidant est la personne responsable des décisions financières (généralement le titulaire de l'officine)"
        )
        hint_decidant.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        hint_decidant.setWordWrap(True)
        decidant_layout.addWidget(hint_decidant)

        ligne_nom_dec = QHBoxLayout()
        self.champ_nom_dec = ChampEditable("Nom :", "nom_decidant")
        self.champ_nom_dec.valeur_changee.connect(self._on_champ_change)
        ligne_nom_dec.addWidget(self.champ_nom_dec)
        self.champ_prenom_dec = ChampEditable("Prénom :", "prenom_decidant")
        self.champ_prenom_dec.valeur_changee.connect(self._on_champ_change)
        ligne_nom_dec.addWidget(self.champ_prenom_dec)
        decidant_layout.addLayout(ligne_nom_dec)

        ligne_contact_dec = QHBoxLayout()
        self.champ_tel_dec = ChampEditable("Téléphone direct :", "telephone_decidant")
        self.champ_tel_dec.valeur_changee.connect(self._on_champ_change)
        ligne_contact_dec.addWidget(self.champ_tel_dec)
        self.champ_email_dec = ChampEditable("Email direct :", "email_decidant")
        self.champ_email_dec.valeur_changee.connect(self._on_champ_change)
        ligne_contact_dec.addWidget(self.champ_email_dec)
        decidant_layout.addLayout(ligne_contact_dec)

        contenu_layout.addWidget(grp_decidant)

        # ── Section Suivi Commercial ──
        grp_suivi = QGroupBox("Suivi Commercial")
        grp_suivi.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #ddd; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        suivi_layout = QVBoxLayout(grp_suivi)

        # Statut + date dernière modification
        ligne_statut = QHBoxLayout()
        lbl_statut = QLabel("Statut :")
        lbl_statut.setFixedWidth(80)
        lbl_statut.setStyleSheet("color: #555;")
        ligne_statut.addWidget(lbl_statut)

        self.combo_statut = QComboBox()
        self.combo_statut.setMinimumHeight(32)
        for s in STATUTS_DISPONIBLES:
            self.combo_statut.addItem(s)
        self.combo_statut.currentTextChanged.connect(self._on_statut_change)
        ligne_statut.addWidget(self.combo_statut)

        self.label_date_statut = QLabel("")
        self.label_date_statut.setStyleSheet("color: #888; font-size: 11px; margin-left: 8px;")
        ligne_statut.addWidget(self.label_date_statut)
        ligne_statut.addStretch()
        suivi_layout.addLayout(ligne_statut)

        # Historique des statuts
        lbl_hist = QLabel("Historique des statuts :")
        lbl_hist.setStyleSheet("color: #555; font-weight: bold; margin-top: 8px;")
        suivi_layout.addWidget(lbl_hist)

        self.historique_statuts = QTextEdit()
        self.historique_statuts.setReadOnly(True)
        self.historique_statuts.setMaximumHeight(100)
        self.historique_statuts.setStyleSheet(
            "QTextEdit { background: #fafafa; border: 1px solid #eee; border-radius: 4px; font-size: 11px; color: #555; }"
        )
        suivi_layout.addWidget(self.historique_statuts)

        # Notes
        lbl_notes = QLabel("Notes :")
        lbl_notes.setStyleSheet("color: #555; font-weight: bold; margin-top: 8px;")
        suivi_layout.addWidget(lbl_notes)

        self.fil_notes = QTextEdit()
        self.fil_notes.setReadOnly(True)
        self.fil_notes.setMinimumHeight(150)
        self.fil_notes.setStyleSheet(
            "QTextEdit { background: #fafafa; border: 1px solid #eee; border-radius: 4px; font-size: 12px; }"
        )
        suivi_layout.addWidget(self.fil_notes)

        # Ajout de note
        ligne_note = QHBoxLayout()
        self.input_nouvelle_note = QTextEdit()
        self.input_nouvelle_note.setPlaceholderText("Saisir une nouvelle note…")
        self.input_nouvelle_note.setMaximumHeight(70)
        self.input_nouvelle_note.setStyleSheet(
            "QTextEdit { border: 1px solid #ddd; border-radius: 4px; padding: 4px; }"
        )
        ligne_note.addWidget(self.input_nouvelle_note)

        btn_ajouter_note = QPushButton("Ajouter\nla note")
        btn_ajouter_note.setFixedWidth(90)
        btn_ajouter_note.setMinimumHeight(60)
        btn_ajouter_note.setStyleSheet(
            "QPushButton { background: #1565C0; color: white; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #0D47A1; }"
        )
        btn_ajouter_note.clicked.connect(self._ajouter_note)
        ligne_note.addWidget(btn_ajouter_note)
        suivi_layout.addLayout(ligne_note)

        contenu_layout.addWidget(grp_suivi)
        contenu_layout.addStretch()

        scroll.setWidget(contenu)
        layout_principal.addWidget(scroll)

    def charger_pharmacie(self, pharmacie_id: int):
        """Charge et affiche les données d'une pharmacie."""
        self.pharmacie_id = pharmacie_id
        pharm = database.get_pharmacie(self.db_path, pharmacie_id)
        if not pharm:
            return

        pharm = dict(pharm)

        self.label_titre_nav.setText(pharm.get("nom", ""))

        # Badge en cible
        if pharm.get("en_cible"):
            self.badge_cible.setText("● EN CIBLE")
            self.badge_cible.setStyleSheet(
                "color: white; background: #2e7d32; border-radius: 4px; padding: 2px 10px; font-weight: bold; font-size: 11px;"
            )
        else:
            self.badge_cible.setText("HORS CIBLE")
            self.badge_cible.setStyleSheet(
                "color: white; background: #757575; border-radius: 4px; padding: 2px 10px; font-size: 11px;"
            )

        # Champs pharmacie
        self.champ_nom.set_valeur(pharm.get("nom", ""))
        self.champ_adresse.set_valeur(pharm.get("adresse", ""))
        self.champ_ville.set_valeur(pharm.get("ville", ""))
        self.champ_cp.set_valeur(pharm.get("code_postal", ""))
        self.champ_dept.set_valeur(pharm.get("departement", ""))
        self.champ_tel.set_valeur(pharm.get("telephone", ""))
        self.champ_fax.set_valeur(pharm.get("fax", ""))
        self.champ_email.set_valeur(pharm.get("email", ""))
        self.champ_ca_tranche.set_valeur(pharm.get("ca_tranche", ""))

        ca_value = pharm.get("ca_value")
        if ca_value:
            self.label_ca_value.setText(f"≈ {int(ca_value):,} €".replace(",", " "))
        else:
            self.label_ca_value.setText("")

        sources_labels = {
            "import_excel": "Import Excel",
            "scraping_pagesjaunes": "Scraping Pages Jaunes",
            "scraping_data_gouv": "Scraping data.gouv.fr",
            "manuel": "Saisie manuelle",
        }
        source = pharm.get("source", "manuel")
        self.label_source.setText(f"Source : {sources_labels.get(source, source)}")

        # Champs décidant
        self.champ_nom_dec.set_valeur(pharm.get("nom_decidant", ""))
        self.champ_prenom_dec.set_valeur(pharm.get("prenom_decidant", ""))
        self.champ_tel_dec.set_valeur(pharm.get("telephone_decidant", ""))
        self.champ_email_dec.set_valeur(pharm.get("email_decidant", ""))

        # Statut
        self._suppression_statut_en_cours = True
        statut = pharm.get("statut", "À contacter")
        idx = self.combo_statut.findText(statut)
        if idx >= 0:
            self.combo_statut.setCurrentIndex(idx)
        self._suppression_statut_en_cours = False

        date_modif = pharm.get("date_modification", "")
        if date_modif:
            self.label_date_statut.setText(f"Dernière modif. : {_fmt_date(date_modif)}")

        # Historique statuts
        self._charger_historique()

        # Notes
        self._charger_notes()

    def _charger_historique(self):
        historique = database.get_historique_statuts(self.db_path, self.pharmacie_id)
        lignes = []
        for h in historique:
            dt = _fmt_date(h["date_heure"])
            auteur = h["auteur"] or "?"
            lignes.append(f"{dt} — {auteur} : {h['ancien_statut']} → {h['nouveau_statut']}")
        self.historique_statuts.setPlainText("\n".join(lignes) if lignes else "Aucun historique.")

    def _charger_notes(self):
        notes = database.get_notes(self.db_path, self.pharmacie_id)
        html = ""
        for note in notes:
            dt = _fmt_date(note["date_heure"])
            auteur = note["auteur"] or "?"
            contenu = note["contenu"] or ""
            html += (
                f'<div style="margin-bottom:8px;">'
                f'<span style="color:#1565C0;font-weight:bold;">[{dt} — {auteur}]</span><br>'
                f'<span style="margin-left:8px;">{contenu}</span>'
                f'</div>'
            )
        self.fil_notes.setHtml(html if html else "<span style='color:#999'>Aucune note.</span>")
        # Scroll vers le bas
        curseur = self.fil_notes.textCursor()
        from PyQt6.QtGui import QTextCursor
        curseur.movePosition(QTextCursor.MoveOperation.End)
        self.fil_notes.setTextCursor(curseur)

    def _on_champ_change(self, nom_champ: str, valeur: str):
        if not self.pharmacie_id:
            return
        database.mettre_a_jour_pharmacie(
            self.db_path,
            self.pharmacie_id,
            {nom_champ: valeur or None}
        )

    def _on_statut_change(self, nouveau_statut: str):
        if self._suppression_statut_en_cours or not self.pharmacie_id:
            return
        database.mettre_a_jour_statut(
            self.db_path,
            self.pharmacie_id,
            nouveau_statut,
            self.prenom_utilisateur,
        )
        self._charger_historique()
        now = datetime.now()
        self.label_date_statut.setText(f"Dernière modif. : {now.strftime('%d/%m/%Y %Hh%M')}")

    def _ajouter_note(self):
        if not self.pharmacie_id:
            return
        contenu = self.input_nouvelle_note.toPlainText().strip()
        if not contenu:
            return
        database.ajouter_note(
            self.db_path,
            self.pharmacie_id,
            contenu,
            self.prenom_utilisateur,
        )
        self.input_nouvelle_note.clear()
        self._charger_notes()

    def set_prenom(self, prenom: str):
        self.prenom_utilisateur = prenom

    def set_db_path(self, db_path: str):
        self.db_path = db_path
