"""
Fiche détaillée d'une pharmacie : informations, décidant, suivi commercial, notes.
Toutes les sauvegardes sont automatiques. Version compatible Mac/Python 3.9+
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTextEdit, QScrollArea, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

import database
from database import STATUTS_DISPONIBLES


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m/%Y %Hh%M")
    except Exception:
        return iso[:16]


def _style_groupe_titre(texte: str) -> QLabel:
    """Crée un titre de section en remplacement de QGroupBox (plus compatible Mac)."""
    lbl = QLabel(texte)
    lbl.setFont(QFont("Arial", 12, QFont.Weight.Bold))
    lbl.setStyleSheet(
        "QLabel { color: #1a237e; border-bottom: 2px solid #1a237e; "
        "padding-bottom: 4px; margin-top: 8px; }"
    )
    return lbl


def _separateur() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("QFrame { border: none; background-color: #e0e0e0; max-height: 1px; }")
    sep.setFixedHeight(1)
    return sep


class ChampEditable(QWidget):
    """Label + LineEdit avec sauvegarde automatique après délai."""

    valeur_changee = pyqtSignal(str, str)

    def __init__(self, label: str, nom_champ: str, parent=None):
        super().__init__(parent)
        self.nom_champ = nom_champ
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._sauvegarder)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        lbl = QLabel(label)
        lbl.setFixedWidth(170)
        lbl.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(lbl)

        self.input = QLineEdit()
        self.input.setMinimumHeight(28)
        self.input.setStyleSheet(
            "QLineEdit { border: 1px solid #ccc; border-radius: 3px; padding: 2px 6px; background: white; }"
            "QLineEdit:focus { border-color: #1565C0; }"
        )
        self.input.textChanged.connect(lambda: self._timer.start(800))
        layout.addWidget(self.input)

    def set_valeur(self, valeur):
        self.input.blockSignals(True)
        self.input.setText(str(valeur) if valeur else "")
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
        self._blocage_statut = False
        self._construire_ui()

    def _construire_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ── Barre de navigation ──
        barre_nav = QFrame()
        barre_nav.setStyleSheet("QFrame { background-color: #f5f5f5; border-bottom: 1px solid #ddd; }")
        barre_nav.setFixedHeight(48)
        nav_layout = QHBoxLayout(barre_nav)
        nav_layout.setContentsMargins(16, 8, 16, 8)

        btn_retour = QPushButton("← Retour a la liste")
        btn_retour.setStyleSheet(
            "QPushButton { background: transparent; color: #1565C0; border: none; font-size: 13px; }"
        )
        btn_retour.setCursor(Qt.CursorShape.PointingHandCursor)
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
        scroll.setStyleSheet("QScrollArea { border: none; background: white; }")

        contenu = QWidget()
        contenu.setStyleSheet("QWidget { background: white; }")
        layout = QVBoxLayout(contenu)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(8)

        # ══ SECTION PHARMACIE ══
        layout.addWidget(_style_groupe_titre("Informations Pharmacie"))

        # Badge en cible
        self.badge_cible = QLabel("")
        self.badge_cible.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.badge_cible.setFixedHeight(24)
        layout.addWidget(self.badge_cible)

        self.champ_nom = ChampEditable("Nom :", "nom")
        self.champ_nom.valeur_changee.connect(self._on_champ_change)
        layout.addWidget(self.champ_nom)

        self.champ_adresse = ChampEditable("Adresse :", "adresse")
        self.champ_adresse.valeur_changee.connect(self._on_champ_change)
        layout.addWidget(self.champ_adresse)

        ligne_geo = QHBoxLayout()
        self.champ_ville = ChampEditable("Ville :", "ville")
        self.champ_ville.valeur_changee.connect(self._on_champ_change)
        ligne_geo.addWidget(self.champ_ville)
        self.champ_cp = ChampEditable("Code postal :", "code_postal")
        self.champ_cp.valeur_changee.connect(self._on_champ_change)
        ligne_geo.addWidget(self.champ_cp)
        self.champ_dept = ChampEditable("Departement :", "departement")
        self.champ_dept.valeur_changee.connect(self._on_champ_change)
        ligne_geo.addWidget(self.champ_dept)
        layout.addLayout(ligne_geo)

        ligne_tel = QHBoxLayout()
        self.champ_tel = ChampEditable("Telephone :", "telephone")
        self.champ_tel.valeur_changee.connect(self._on_champ_change)
        ligne_tel.addWidget(self.champ_tel)
        self.champ_fax = ChampEditable("Fax :", "fax")
        self.champ_fax.valeur_changee.connect(self._on_champ_change)
        ligne_tel.addWidget(self.champ_fax)
        layout.addLayout(ligne_tel)

        self.champ_email = ChampEditable("Email general :", "email")
        self.champ_email.valeur_changee.connect(self._on_champ_change)
        layout.addWidget(self.champ_email)

        ligne_ca = QHBoxLayout()
        self.champ_ca = ChampEditable("CA tranche :", "ca_tranche")
        self.champ_ca.valeur_changee.connect(self._on_champ_change)
        ligne_ca.addWidget(self.champ_ca)
        self.label_ca_value = QLabel("")
        self.label_ca_value.setStyleSheet("color: #2e7d32; font-size: 12px; font-weight: bold;")
        ligne_ca.addWidget(self.label_ca_value)
        ligne_ca.addStretch()
        layout.addLayout(ligne_ca)

        self.label_source = QLabel("")
        self.label_source.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        layout.addWidget(self.label_source)

        layout.addWidget(_separateur())

        # ══ SECTION DECIDANT ══
        layout.addWidget(_style_groupe_titre("Pharmacien titulaire / Proprietaire"))

        hint = QLabel("Le decidant est la personne responsable des decisions financieres (generalement le titulaire).")
        hint.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        ligne_nom_dec = QHBoxLayout()
        self.champ_nom_dec = ChampEditable("Nom :", "nom_decidant")
        self.champ_nom_dec.valeur_changee.connect(self._on_champ_change)
        ligne_nom_dec.addWidget(self.champ_nom_dec)
        self.champ_prenom_dec = ChampEditable("Prenom :", "prenom_decidant")
        self.champ_prenom_dec.valeur_changee.connect(self._on_champ_change)
        ligne_nom_dec.addWidget(self.champ_prenom_dec)
        layout.addLayout(ligne_nom_dec)

        ligne_contact_dec = QHBoxLayout()
        self.champ_tel_dec = ChampEditable("Telephone direct :", "telephone_decidant")
        self.champ_tel_dec.valeur_changee.connect(self._on_champ_change)
        ligne_contact_dec.addWidget(self.champ_tel_dec)
        self.champ_email_dec = ChampEditable("Email direct :", "email_decidant")
        self.champ_email_dec.valeur_changee.connect(self._on_champ_change)
        ligne_contact_dec.addWidget(self.champ_email_dec)
        layout.addLayout(ligne_contact_dec)

        layout.addWidget(_separateur())

        # ══ SECTION SUIVI COMMERCIAL ══
        layout.addWidget(_style_groupe_titre("Suivi Commercial"))

        ligne_statut = QHBoxLayout()
        lbl_s = QLabel("Statut :")
        lbl_s.setFixedWidth(80)
        lbl_s.setStyleSheet("color: #555;")
        ligne_statut.addWidget(lbl_s)

        self.combo_statut = QComboBox()
        self.combo_statut.setMinimumHeight(30)
        self.combo_statut.setStyleSheet(
            "QComboBox { border: 1px solid #ccc; border-radius: 3px; padding: 2px 8px; background: white; }"
        )
        for s in STATUTS_DISPONIBLES:
            self.combo_statut.addItem(s)
        self.combo_statut.currentTextChanged.connect(self._on_statut_change)
        ligne_statut.addWidget(self.combo_statut)

        self.label_date_statut = QLabel("")
        self.label_date_statut.setStyleSheet("color: #888; font-size: 11px; margin-left: 8px;")
        ligne_statut.addWidget(self.label_date_statut)
        ligne_statut.addStretch()
        layout.addLayout(ligne_statut)

        # Historique statuts
        lbl_hist = QLabel("Historique des statuts :")
        lbl_hist.setStyleSheet("color: #555; font-weight: bold; margin-top: 8px;")
        layout.addWidget(lbl_hist)

        self.historique_statuts = QTextEdit()
        self.historique_statuts.setReadOnly(True)
        self.historique_statuts.setMaximumHeight(90)
        self.historique_statuts.setStyleSheet(
            "QTextEdit { background: #fafafa; border: 1px solid #eee; "
            "border-radius: 3px; font-size: 11px; color: #555; }"
        )
        layout.addWidget(self.historique_statuts)

        # Notes
        lbl_notes = QLabel("Notes :")
        lbl_notes.setStyleSheet("color: #555; font-weight: bold; margin-top: 8px;")
        layout.addWidget(lbl_notes)

        self.fil_notes = QTextEdit()
        self.fil_notes.setReadOnly(True)
        self.fil_notes.setMinimumHeight(140)
        self.fil_notes.setStyleSheet(
            "QTextEdit { background: #fafafa; border: 1px solid #eee; border-radius: 3px; font-size: 12px; }"
        )
        layout.addWidget(self.fil_notes)

        # Saisie nouvelle note
        ligne_note = QHBoxLayout()
        self.input_note = QTextEdit()
        self.input_note.setPlaceholderText("Saisir une nouvelle note...")
        self.input_note.setMaximumHeight(65)
        self.input_note.setStyleSheet(
            "QTextEdit { border: 1px solid #ccc; border-radius: 3px; padding: 4px; background: white; }"
        )
        ligne_note.addWidget(self.input_note)

        btn_note = QPushButton("Ajouter\nla note")
        btn_note.setFixedWidth(90)
        btn_note.setMinimumHeight(60)
        btn_note.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; border-radius: 4px; font-weight: bold; }"
            "QPushButton:pressed { background-color: #0D47A1; }"
        )
        btn_note.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_note.clicked.connect(self._ajouter_note)
        ligne_note.addWidget(btn_note)
        layout.addLayout(ligne_note)

        layout.addStretch()

        scroll.setWidget(contenu)
        layout_principal.addWidget(scroll)

    def charger_pharmacie(self, pharmacie_id: int):
        self.pharmacie_id = pharmacie_id
        try:
            pharm = database.get_pharmacie(self.db_path, pharmacie_id)
        except Exception:
            return
        if not pharm:
            return
        pharm = dict(pharm)

        self.label_titre_nav.setText(pharm.get("nom", ""))

        if pharm.get("en_cible"):
            self.badge_cible.setText("EN CIBLE")
            self.badge_cible.setStyleSheet(
                "QLabel { color: white; background-color: #2e7d32; border-radius: 3px; "
                "padding: 2px 10px; font-weight: bold; font-size: 11px; }"
            )
        else:
            self.badge_cible.setText("HORS CIBLE")
            self.badge_cible.setStyleSheet(
                "QLabel { color: white; background-color: #757575; border-radius: 3px; "
                "padding: 2px 10px; font-size: 11px; }"
            )

        self.champ_nom.set_valeur(pharm.get("nom"))
        self.champ_adresse.set_valeur(pharm.get("adresse"))
        self.champ_ville.set_valeur(pharm.get("ville"))
        self.champ_cp.set_valeur(pharm.get("code_postal"))
        self.champ_dept.set_valeur(pharm.get("departement"))
        self.champ_tel.set_valeur(pharm.get("telephone"))
        self.champ_fax.set_valeur(pharm.get("fax"))
        self.champ_email.set_valeur(pharm.get("email"))
        self.champ_ca.set_valeur(pharm.get("ca_tranche"))

        ca = pharm.get("ca_value")
        self.label_ca_value.setText(f"environ {int(ca):,} EUR".replace(",", " ") if ca else "")

        sources = {
            "import_excel": "Import Excel",
            "scraping_pagesjaunes": "Scraping Pages Jaunes",
            "scraping_data_gouv": "Scraping data.gouv.fr",
            "manuel": "Saisie manuelle",
        }
        self.label_source.setText(f"Source : {sources.get(pharm.get('source', 'manuel'), pharm.get('source', ''))}")

        self.champ_nom_dec.set_valeur(pharm.get("nom_decidant"))
        self.champ_prenom_dec.set_valeur(pharm.get("prenom_decidant"))
        self.champ_tel_dec.set_valeur(pharm.get("telephone_decidant"))
        self.champ_email_dec.set_valeur(pharm.get("email_decidant"))

        self._blocage_statut = True
        statut = pharm.get("statut", "A contacter")
        idx = self.combo_statut.findText(statut)
        if idx >= 0:
            self.combo_statut.setCurrentIndex(idx)
        self._blocage_statut = False

        date_m = pharm.get("date_modification", "")
        if date_m:
            self.label_date_statut.setText(f"Modifie le {_fmt_date(date_m)}")

        self._charger_historique()
        self._charger_notes()

    def _charger_historique(self):
        try:
            historique = database.get_historique_statuts(self.db_path, self.pharmacie_id)
        except Exception:
            return
        lignes = []
        for h in historique:
            dt = _fmt_date(h["date_heure"])
            auteur = h["auteur"] or "?"
            lignes.append(f"{dt} - {auteur} : {h['ancien_statut']} -> {h['nouveau_statut']}")
        self.historique_statuts.setPlainText(
            "\n".join(lignes) if lignes else "Aucun historique."
        )

    def _charger_notes(self):
        try:
            notes = database.get_notes(self.db_path, self.pharmacie_id)
        except Exception:
            return

        lignes = []
        for note in notes:
            dt = _fmt_date(note["date_heure"])
            auteur = note["auteur"] or "?"
            contenu = note["contenu"] or ""
            lignes.append(f"[{dt} - {auteur}]\n{contenu}\n")

        self.fil_notes.setPlainText("\n".join(lignes) if lignes else "Aucune note.")

        # Scroll vers le bas après un court délai (compatible Mac)
        QTimer.singleShot(50, self._scroll_notes_bas)

    def _scroll_notes_bas(self):
        sb = self.fil_notes.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_champ_change(self, nom_champ: str, valeur: str):
        if not self.pharmacie_id:
            return
        try:
            database.mettre_a_jour_pharmacie(
                self.db_path, self.pharmacie_id, {nom_champ: valeur or None}
            )
        except Exception:
            pass

    def _on_statut_change(self, nouveau_statut: str):
        if self._blocage_statut or not self.pharmacie_id:
            return
        try:
            database.mettre_a_jour_statut(
                self.db_path, self.pharmacie_id, nouveau_statut, self.prenom_utilisateur
            )
            self._charger_historique()
            now = datetime.now()
            self.label_date_statut.setText(f"Modifie le {now.strftime('%d/%m/%Y %Hh%M')}")
        except Exception:
            pass

    def _ajouter_note(self):
        if not self.pharmacie_id:
            return
        contenu = self.input_note.toPlainText().strip()
        if not contenu:
            return
        try:
            database.ajouter_note(
                self.db_path, self.pharmacie_id, contenu, self.prenom_utilisateur
            )
            self.input_note.clear()
            self._charger_notes()
        except Exception:
            pass

    def set_prenom(self, prenom: str):
        self.prenom_utilisateur = prenom

    def set_db_path(self, db_path: str):
        self.db_path = db_path
