# Heliantys — Application de Gestion de la Prospection Commerciale

Application desktop Python/PyQt6 pour gérer la prospection des pharmacies françaises en vue de l'installation de bornes interactives Heliantys.

---

## Prérequis

- **Python 3.11 ou supérieur** — [Télécharger Python](https://www.python.org/downloads/)
- Windows 10/11, macOS 12+ ou Linux
- Connexion Internet (pour le scraping et l'enrichissement)

---

## Installation pas à pas

### 1. Installer Python 3.11+

Vérifier votre version Python :
```bash
python --version
```
Si la version est inférieure à 3.11, téléchargez Python sur python.org.

### 2. Télécharger ou cloner le projet

Placez le dossier `heliantys/` à l'emplacement de votre choix (par ex. `C:\Heliantys\`).

### 3. Installer les dépendances

Ouvrez un terminal dans le dossier du projet :

```bash
pip install -r requirements.txt
```

> Sur certains systèmes, utilisez `pip3` à la place de `pip`.

### 4. Placer le fichier de données Excel

Copiez le fichier `Copie_de_Pharma_pour_vadim.xlsx` à la racine du projet (même dossier que `main.py`).

### 5. Lancer l'application

```bash
python main.py
```

---

## Configuration au premier lancement

Au premier démarrage, une fenêtre de configuration s'affiche :

1. **Votre prénom** — utilisé pour horodater vos notes et historiques d'activité.
2. **Chemin vers la base de données** — peut pointer vers un fichier `.db` partagé sur OneDrive pour travailler en équipe.
3. **Token API Pappers** — optionnel, améliore la détection des pharmaciens titulaires.

### Utilisation en équipe (OneDrive partagé)

Pour que toute l'équipe partage la même base :
1. Créez le fichier `.db` sur un dossier OneDrive partagé (ex : `C:\Users\Jean\OneDrive\Heliantys\heliantys.db`).
2. Sur chaque poste, indiquez le chemin vers ce même fichier lors du premier lancement.
3. Le fichier `config.json` reste local à chaque poste (prénom différent par poste).

---

## Fonctionnalités

### Import initial
- L'application propose automatiquement d'importer le fichier Excel si la base est vide.
- Les pharmacies avec CA ≥ 5 MF sont automatiquement marquées "En cible".
- L'import est idempotent : pas de doublons créés.

### Tableau de bord
- KPI globaux (total, en cible, non contactées)
- Graphique de répartition par statut
- Top 5 départements
- Dernières pharmacies modifiées

### Gestion des pharmacies
- Filtres : recherche texte, département, statut, en cible, non enrichies
- Fiche détaillée avec sauvegarde automatique
- Historique complet des statuts horodaté
- Fil chronologique de notes (non modifiables après saisie)

### Scraping région
- API annuaire santé (data.gouv.fr) — source officielle
- Pages Jaunes — extraction complémentaire
- Anti-doublon automatique

### Enrichissement automatique
- Pappers API (dirigeants/titulaires)
- Recherche email
- Enrichissement par lot avec barre de progression

---

## Structure des fichiers

```
heliantys/
├── main.py                 # Point d'entrée
├── database.py             # Base SQLite (CRUD)
├── importer.py             # Import Excel
├── enricher.py             # Enrichissement automatique
├── scraper.py              # Scraping région
├── config.json             # Config locale (NE PAS partager sur OneDrive)
├── heliantys.db            # Base de données (ou sur OneDrive partagé)
├── requirements.txt
├── README.md
└── ui/
    ├── main_window.py      # Fenêtre principale
    ├── setup_wizard.py     # Assistant premier lancement
    ├── pharmacie_list.py   # Liste avec filtres
    ├── pharmacie_detail.py # Fiche détaillée
    ├── scraping_dialog.py  # Fenêtre scraping
    ├── dashboard.py        # Tableau de bord
    └── settings.py         # Paramètres
```

---

## Notes techniques

- La base SQLite utilise le mode WAL (Write-Ahead Logging) pour la compatibilité multi-postes sur OneDrive.
- Toutes les sauvegardes de fiches sont automatiques (délai de 800ms après la dernière frappe).
- Les notes ne sont pas modifiables après saisie (traçabilité fidèle).
- Les logs sont enregistrés dans `heliantys.log` à la racine du projet.

---

## Support

En cas de problème, vérifiez :
1. `python --version` → doit afficher 3.11 ou supérieur
2. Que toutes les dépendances sont installées (`pip install -r requirements.txt`)
3. Que le chemin OneDrive est accessible et que le fichier `.db` n'est pas verrouillé par un autre processus
