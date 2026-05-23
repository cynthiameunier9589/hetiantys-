"""
Point d'entrée principal — Prospection de parapharmacies en France.
Lance les 4 phases : OSM → INSEE → Pappers → Email Finder, puis exporte en Excel.
"""

import sys
import os
import glob
import json
from datetime import datetime

# Vérification Python avant tout import
if sys.version_info < (3, 8):
    print("ERREUR : Python 3.8 ou supérieur requis.")
    print(f"Version actuelle : {sys.version}")
    sys.exit(1)

# Ajouter le dossier de l'application au path Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BASE_DIR, creer_logger, normaliser_nom_fichier
import modules.osm as osm
import modules.insee as insee
import modules.pappers as pappers
import modules.email_finder as email_finder
import modules.export as export

logger = creer_logger("lancer")


def afficher_menu() -> None:
    """Affiche le menu principal de l'application."""
    print("\n╔══════════════════════════════════════╗")
    print("║     PROSPECTION PARAPHARMACIE        ║")
    print("╚══════════════════════════════════════╝")
    print("  1. Nouvelle recherche")
    print("  2. Voir les dernières recherches")
    print("  3. Relancer une recherche précédente")
    print("  4. Quitter\n")


def choisir_option() -> str:
    """Valide le choix de menu (boucle jusqu'à saisie correcte)."""
    while True:
        choix = input("Votre choix (1/2/3/4) : ").strip()
        if choix in ("1", "2", "3", "4"):
            return choix
        print("Choix invalide, entrez 1, 2, 3 ou 4")


def lister_fichiers_exports() -> list:
    """Retourne les fichiers Excel triés par date de modification (plus récent d'abord)."""
    fichiers = glob.glob(os.path.join(BASE_DIR, "exports", "prospection_*.xlsx"))
    return sorted(fichiers, key=os.path.getmtime, reverse=True)


def afficher_recherches() -> None:
    """Affiche la liste des recherches précédentes."""
    fichiers = lister_fichiers_exports()
    if not fichiers:
        print("\n  [INFO] Aucune recherche précédente trouvée.")
        return

    print(f"\n  {'='*50}")
    print("  DERNIÈRES RECHERCHES :")
    print(f"  {'='*50}")
    for i, f in enumerate(fichiers[:10], 1):
        nom = os.path.basename(f)
        date = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d/%m/%Y %H:%M")
        taille = os.path.getsize(f) // 1024
        print(f"  {i:2}. {nom}  ({date}, {taille} Ko)")
    print(f"  {'='*50}")


def extraire_zone_depuis_nom_fichier(nom_fichier: str) -> str:
    """Extrait le nom de la zone depuis un nom de fichier export."""
    # Format : prospection_[zone]_[YYYYMMDD].xlsx
    base = os.path.basename(nom_fichier)
    base = base.replace("prospection_", "").replace(".xlsx", "").replace("_partiel", "")
    parties = base.rsplit("_", 1)
    # La dernière partie est la date (8 chiffres)
    if len(parties) == 2 and parties[1].isdigit() and len(parties[1]) == 8:
        return parties[0].replace("_", " ")
    return base


def choisir_recherche_precedente() -> str:
    """Permet de sélectionner une zone depuis les recherches précédentes."""
    fichiers = lister_fichiers_exports()
    if not fichiers:
        print("\n  [INFO] Aucune recherche précédente disponible.")
        return ""

    afficher_recherches()
    limite = min(len(fichiers), 10)

    while True:
        saisie = input(f"\n  Numéro (1-{limite}) : ").strip()
        try:
            idx = int(saisie) - 1
            if 0 <= idx < limite:
                zone = extraire_zone_depuis_nom_fichier(fichiers[idx])
                return zone
        except ValueError:
            pass
        print(f"  Entrez un numéro entre 1 et {limite}")


def executer_pipeline(zone: str, force_refresh: bool = False) -> None:
    """
    Exécute le pipeline complet : OSM → INSEE → Pappers → Email → Export.
    Sauvegarde les données partielles en cas d'erreur.
    """
    donnees = []

    try:
        # Phase 1 : OSM
        print(f"\n  [1/4] Recherche des parapharmacies...")
        donnees = osm.rechercher(zone, force_refresh)
        print(f"  [OK] {len(donnees)} parapharmacies trouvées")

        if not donnees:
            print("  Arrêt : aucune donnée à enrichir.")
            return

        # Phase 2 : INSEE
        print(f"\n  [2/4] Enrichissement légal (INSEE)...")
        donnees = insee.enrichir(donnees, zone)
        avec_siret = sum(1 for p in donnees if p.siret)
        print(f"  [OK] {avec_siret}/{len(donnees)} enrichis avec SIRET")

        # Phase 3 : Pappers (CA)
        print(f"\n  [3/4] Récupération des CA (Pappers)...")
        donnees = pappers.enrichir(donnees, zone)
        avec_ca = sum(1 for p in donnees if p.chiffre_affaires)
        print(f"  [OK] {avec_ca}/{len(donnees)} CA récupérés")

        # Phase 4 : Email finder
        print(f"\n  [4/4] Recherche des emails...")
        donnees = email_finder.enrichir(donnees)
        avec_email = sum(1 for p in donnees if p.email)
        print(f"  [OK] {avec_email}/{len(donnees)} emails trouvés")

        # Export Excel
        print(f"\n  Génération du fichier Excel...")
        chemin = export.generer(donnees, zone)
        print(f"\n  ╔══════════════════════════════════════════╗")
        print(f"  ║  [SUCCÈS] Fichier disponible :           ║")
        print(f"  ║  {os.path.basename(chemin):<40}║")
        print(f"  ╚══════════════════════════════════════════╝")
        print(f"  Chemin : {chemin}")
        logger.info(f"Pipeline complet pour '{zone}' → {chemin}")

    except KeyboardInterrupt:
        print(f"\n\n  [INTERRUPTION] Recherche interrompue par l'utilisateur.")
        if donnees:
            try:
                chemin_partiel = export.generer(donnees, zone, partiel=True)
                print(f"  [SAUVEGARDE] Données partielles : {os.path.basename(chemin_partiel)}")
            except Exception:
                pass

    except Exception as e:
        import traceback
        erreur_complete = traceback.format_exc()
        logger.error(f"Erreur pipeline pour '{zone}' : {erreur_complete}")

        # Sauvegarde partielle avant d'afficher l'erreur
        if donnees:
            try:
                chemin_partiel = export.generer(donnees, zone, partiel=True)
                print(f"\n  [SAUVEGARDE] Données partielles : {os.path.basename(chemin_partiel)}")
            except Exception:
                pass

        print(f"\n  [ERREUR] {str(e)}")
        print("  Détails complets dans logs/")


def nouvelle_recherche() -> None:
    """Interface pour lancer une nouvelle recherche."""
    # Saisie de la zone géographique
    while True:
        zone = input("\n  Ville, département ou région ? ").strip()
        if zone:
            break
        print("  Veuillez saisir une zone.")

    force = input("  Forcer le rafraîchissement du cache ? (o/N) ").strip()
    force_refresh = force.lower() == 'o'

    executer_pipeline(zone, force_refresh)


def relancer_recherche() -> None:
    """Relance une recherche précédente avec rafraîchissement du cache."""
    zone = choisir_recherche_precedente()
    if not zone:
        return

    print(f"\n  [INFO] Relance de la recherche pour : '{zone}'")
    executer_pipeline(zone, force_refresh=True)


def main() -> None:
    """Boucle principale du programme."""
    while True:
        afficher_menu()
        choix = choisir_option()

        if choix == "1":
            nouvelle_recherche()

        elif choix == "2":
            afficher_recherches()

        elif choix == "3":
            relancer_recherche()

        elif choix == "4":
            print("\n  Au revoir !\n")
            break

        if choix != "4":
            input("\n  Appuyez sur Entrée pour continuer...")


if __name__ == "__main__":
    main()
