/**
 * Google Apps Script — Formulaire Parrainage Make Your Stand
 *
 * DÉPLOIEMENT : voir instructions dans DEPLOY_INSTRUCTIONS.md
 *
 * Champs attendus dans le POST JSON :
 *   cadeau, entreprise_parrain, entreprise_filleul,
 *   contact_nom, contact_tel, contact_email, date
 */

// ─── CONFIGURATION ────────────────────────────────────────────────────────────
var SHEET_NAME = "Parrainages"; // Nom de l'onglet dans le Google Sheet
// ──────────────────────────────────────────────────────────────────────────────

var HEADERS = [
  "Date réception",
  "Cadeau choisi",
  "Entreprise parrain",
  "Entreprise filleul",
  "Nom contact",
  "Téléphone",
  "Email",
  "Date souhaitée"
];

/**
 * Point d'entrée HTTP POST.
 * Le formulaire envoie : Content-Type application/json avec mode no-cors.
 * En no-cors le navigateur envoie le body en text/plain — on parse quand même.
 */
function doPost(e) {
  try {
    var raw  = e.postData && e.postData.contents ? e.postData.contents : "{}";
    var data = JSON.parse(raw);

    var sheet = getOrCreateSheet_();

    var now = new Date();
    var row = [
      Utilities.formatDate(now, Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm:ss"),
      sanitize_(data.cadeau),
      sanitize_(data.entreprise_parrain),
      sanitize_(data.entreprise_filleul),
      sanitize_(data.contact_nom),
      sanitize_(data.contact_tel),
      sanitize_(data.contact_email),
      sanitize_(data.date)
    ];

    sheet.appendRow(row);

    return jsonResponse_({ status: "ok", message: "Parrainage enregistré." });

  } catch (err) {
    Logger.log("Erreur doPost : " + err.message);
    return jsonResponse_({ status: "error", message: err.message });
  }
}

function doGet(e) {
  return jsonResponse_({ status: "ok", message: "Service parrainage actif." });
}

// ─── FEUILLE ──────────────────────────────────────────────────────────────────

function getOrCreateSheet_() {
  var ss    = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);

  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }

  // Ligne d'en-tête automatique si la feuille est vide
  if (sheet.getLastRow() === 0) {
    var headerRow = sheet.getRange(1, 1, 1, HEADERS.length);
    headerRow.setValues([HEADERS]);
    headerRow.setFontWeight("bold");
    headerRow.setBackground("#1F4496");
    headerRow.setFontColor("#ffffff");
    sheet.setFrozenRows(1);
    sheet.setColumnWidth(1, 160);
    sheet.setColumnWidth(2, 200);
    sheet.setColumnWidth(3, 200);
    sheet.setColumnWidth(4, 200);
    sheet.setColumnWidth(5, 160);
    sheet.setColumnWidth(6, 140);
    sheet.setColumnWidth(7, 220);
    sheet.setColumnWidth(8, 140);
  }

  return sheet;
}

// ─── UTILITAIRES ─────────────────────────────────────────────────────────────

function sanitize_(val) {
  if (val === undefined || val === null) return "";
  return String(val).trim();
}

function jsonResponse_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
