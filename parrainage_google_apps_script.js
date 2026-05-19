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
var SHEET_NAME      = "Parrainages";          // Nom de l'onglet dans le Google Sheet
var NOTIFY_EMAIL    = "hello@makeyourstand.fr";
var NOTIFY_SUBJECT  = "🎉 Nouveau parrainage reçu — Make Your Stand";
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
 * Le formulaire envoie : Content-Type application/json
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
    sendNotificationEmail_(data, now);

    return jsonResponse_({ status: "ok", message: "Parrainage enregistré." });

  } catch (err) {
    Logger.log("Erreur doPost : " + err.message);
    return jsonResponse_({ status: "error", message: err.message }, 500);
  }
}

// Renvoie une réponse CORS-compatible (nécessaire pour fetch depuis une page HTML)
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

// ─── EMAIL ────────────────────────────────────────────────────────────────────

function sendNotificationEmail_(data, receivedAt) {
  var dateStr = Utilities.formatDate(
    receivedAt,
    Session.getScriptTimeZone(),
    "dd/MM/yyyy 'à' HH:mm"
  );

  var body =
    "Bonjour,\n\n" +
    "Un nouveau parrainage vient d'être soumis via le site Make Your Stand.\n\n" +
    "────────────────────────────────\n" +
    "DÉTAILS DU PARRAINAGE\n" +
    "────────────────────────────────\n" +
    "📅 Reçu le       : " + dateStr + "\n" +
    "🎁 Cadeau choisi : " + sanitize_(data.cadeau) + "\n\n" +
    "🏢 Entreprise parrain  : " + sanitize_(data.entreprise_parrain) + "\n" +
    "🏢 Entreprise filleul  : " + sanitize_(data.entreprise_filleul) + "\n\n" +
    "👤 Nom du contact : " + sanitize_(data.contact_nom) + "\n" +
    "📞 Téléphone      : " + sanitize_(data.contact_tel) + "\n" +
    "✉️  Email          : " + sanitize_(data.contact_email) + "\n" +
    "📆 Date souhaitée : " + sanitize_(data.date) + "\n" +
    "────────────────────────────────\n\n" +
    "Ces données ont été ajoutées automatiquement dans le Google Sheet « " + SHEET_NAME + " ».\n\n" +
    "— Make Your Stand (notification automatique)";

  var htmlBody =
    "<div style='font-family:sans-serif;max-width:600px'>" +
    "<div style='background:#5A3B9B;padding:20px;border-radius:8px 8px 0 0'>" +
    "<h2 style='color:#fff;margin:0'>🎉 Nouveau parrainage Make Your Stand</h2>" +
    "</div>" +
    "<div style='border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 8px 8px'>" +
    "<p style='color:#555;margin-top:0'>Reçu le <strong>" + dateStr + "</strong></p>" +
    "<table style='width:100%;border-collapse:collapse'>" +
    row_("🎁 Cadeau choisi",      data.cadeau) +
    row_("🏢 Entreprise parrain",  data.entreprise_parrain) +
    row_("🏢 Entreprise filleul",  data.entreprise_filleul) +
    row_("👤 Nom du contact",      data.contact_nom) +
    row_("📞 Téléphone",           data.contact_tel) +
    row_("✉️ Email",               data.contact_email) +
    row_("📆 Date souhaitée",      data.date) +
    "</table>" +
    "<p style='margin-top:20px;color:#888;font-size:12px'>" +
    "Ces données ont été enregistrées automatiquement dans le Google Sheet « " + SHEET_NAME + " »." +
    "</p></div></div>";

  MailApp.sendEmail({
    to:       NOTIFY_EMAIL,
    subject:  NOTIFY_SUBJECT,
    body:     body,
    htmlBody: htmlBody
  });
}

// ─── UTILITAIRES ─────────────────────────────────────────────────────────────

function row_(label, value) {
  return "<tr>" +
    "<td style='padding:8px 12px;background:#f5f5f5;font-weight:bold;width:40%;border-bottom:1px solid #eee'>" + label + "</td>" +
    "<td style='padding:8px 12px;border-bottom:1px solid #eee'>" + sanitize_(value) + "</td>" +
    "</tr>";
}

function sanitize_(val) {
  if (val === undefined || val === null) return "";
  return String(val).trim();
}

function jsonResponse_(obj, code) {
  var output = ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
  return output;
}
