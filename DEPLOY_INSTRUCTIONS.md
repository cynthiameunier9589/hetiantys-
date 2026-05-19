# Déploiement — Script Parrainage Google Sheets

## Étape 1 — Créer le Google Sheet

1. Ouvre [sheets.google.com](https://sheets.google.com) et crée un nouveau classeur.
2. Donne-lui un nom (ex. : **Parrainages MYS**).  
   > L'onglet s'appellera automatiquement **Parrainages** (créé par le script à la première soumission). Tu peux en créer un à l'avance avec ce nom exact si tu veux.

---

## Étape 2 — Ouvrir l'éditeur Apps Script

Dans le Google Sheet :  
**Extensions → Apps Script**

---

## Étape 3 — Coller le script

1. Supprime tout le code par défaut dans `Code.gs`.
2. Copie-colle **tout le contenu** du fichier `parrainage_google_apps_script.js`.
3. Clique sur **💾 Enregistrer** (ou `Ctrl+S`).

---

## Étape 4 — Déployer en Application Web

1. Clique sur le bouton **Déployer** (en haut à droite) → **Nouveau déploiement**.
2. Clique sur l'engrenage ⚙️ à côté de "Sélectionner le type" → choisis **Application Web**.
3. Configure :
   | Champ | Valeur |
   |---|---|
   | Description | Parrainage MYS v1 |
   | Exécuter en tant que | **Moi** (ton compte Google) |
   | Qui a accès | **Tout le monde** *(sans connexion requise)* |
4. Clique sur **Déployer**.
5. **Autorise les permissions** demandées (accès Sheets + Gmail) avec ton compte Google.
6. Copie l'**URL de l'application Web** affichée — elle ressemble à :  
   ```
   https://script.google.com/macros/s/XXXXXXXXXXXXXXXXXXXX/exec
   ```

---

## Étape 5 — Brancher l'URL dans le HTML

Dans le fichier `parrainagemys.html`, repère la ligne du `fetch` POST (cherche `fetch(`), et remplace l'URL webhook actuelle par celle copiée à l'étape précédente :

```js
fetch("https://script.google.com/macros/s/XXXXXXXXXXXXXXXXXXXX/exec", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload)
})
```

---

## Étape 6 — Tester

1. Ouvre le site HTML dans un navigateur.
2. Remplis et soumets le formulaire de parrainage.
3. Vérifie :
   - Le Google Sheet contient une ligne avec les données + une ligne d'en-tête bleue.
   - `hello@makeyourstand.fr` a reçu l'email de notification.

---

## Modifier le script plus tard

Toute modification du script nécessite un **nouveau déploiement** :  
**Déployer → Gérer les déploiements → ✏️ Modifier → Nouvelle version → Déployer**

L'URL reste la même si tu utilises "Gérer les déploiements" au lieu d'en créer un nouveau.

---

## Note CORS

Google Apps Script renvoie les réponses sans en-têtes CORS personnalisables.  
Le `fetch` depuis le navigateur peut afficher une erreur CORS en console **même si les données sont bien enregistrées**. Pour éviter ce comportement :

- Utilise `mode: "no-cors"` dans le fetch, ou
- Passe par un proxy/serverless pour relayer la requête.

Si tu veux qu'on adapte le HTML en `no-cors`, demande-le.
