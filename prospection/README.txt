━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PROSPECTION PARAPHARMACIE FRANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Saisissez une ville, un département ou une région française,
et obtenez un fichier Excel avec toutes les parapharmacies
de la zone + infos légales, CA et emails.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. PRÉREQUIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Python 3.8 ou supérieur
  Vérifier : python --version


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. INSTALLATION (2 commandes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  pip install -r requirements.txt
  python lancer.py


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. CLÉ API INSEE (gratuite, optionnelle)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Sans elle : nom, adresse, téléphone, email, CA uniquement
  Avec elle : + SIRET, dirigeant, statut juridique

  Étapes :
    1. https://portail-api.insee.fr/  →  Créer un compte
    2. Créer une application, souscrire à l'API "Sirene"
    3. Copier la Consumer Key ET la Consumer Secret
    4. Coller dans config.py :
       INSEE_API_KEY = "consumer_key:consumer_secret"


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. UTILISATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python lancer.py
  → choisir 1 (Nouvelle recherche)
  → saisir "Lyon"  (ou "Rhône", "Auvergne-Rhône-Alpes", etc.)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. RÉSULTATS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Fichier Excel dans le dossier  exports/
  3 onglets :
    - Parapharmacies  : toutes les données + colonnes prospection
    - Résumé          : statistiques de la recherche
    - Sources         : limites et sources de données


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. LIMITES CONNUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - OSM peut manquer certaines parapharmacies (données collaboratives)
  - CA avec 1-2 ans de retard sur Pappers
  - Emails absents pour ~70% des entrées (non publiés sur les sites)
  - Pappers peut ralentir le script (pauses anti-blocage automatiques)
  - INSEE nécessite une clé API (gratuite mais à demander sur api.insee.fr)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7. EN CAS DE PROBLÈME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Consulter les logs dans  logs/
  Les données partielles sont sauvegardées dans  cache/
  Relancer : le pipeline reprend depuis le cache si disponible

  Tests individuels des modules :
    python modules/osm.py
    python modules/insee.py
    python modules/pappers.py
    python modules/email_finder.py
    python modules/export.py


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8. STRUCTURE DES FICHIERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  prospection/
  ├── lancer.py           ← point d'entrée
  ├── config.py           ← configuration, constantes, utilitaires
  ├── requirements.txt    ← dépendances Python
  ├── README.txt          ← ce fichier
  ├── cache/              ← données intermédiaires (JSON)
  ├── exports/            ← fichiers Excel générés
  ├── logs/               ← journaux d'exécution
  └── modules/
      ├── modeles.py      ← structure de données commune
      ├── osm.py          ← recherche OpenStreetMap
      ├── insee.py        ← enrichissement légal INSEE Sirene
      ├── pappers.py      ← chiffre d'affaires Pappers.fr
      ├── email_finder.py ← extraction d'emails sur les sites web
      └── export.py       ← génération Excel
