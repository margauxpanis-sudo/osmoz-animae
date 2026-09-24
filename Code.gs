/**
 * Pont formulaire -> moteur — Osmoz Animae
 * ==========================================
 *
 * Volontairement "bête" : ce script ne fait AUCUNE interprétation (pas de
 * comptage d'animaux, pas de lecture de la contrainte horaire, pas de
 * conversion jour -> index). Il se contente d'exporter les réponses du
 * formulaire telles quelles, en JSON, colonne par colonne.
 *
 * Pourquoi séparer comme ça : ce script tourne dans le vrai compte Google
 * de Margaux/Ludivine, où il ne peut pas être testé avant coup depuis une
 * session Claude. Toute la partie qui demande de l'interprétation (compter
 * les animaux dans "2 chevaux, 1 chien", comprendre "pas avant 16h", etc.)
 * est faite côté Python (form_import.py, dans le même dossier que le
 * moteur) où elle a pu être testée sur des cas réels avant d'être utilisée
 * pour de vrai. Ce script-ci n'a donc presque rien qui puisse casser.
 *
 * INSTALLATION (à faire une fois par Margaux ou Ludivine) :
 *   1. Ouvrir la feuille de réponses du Google Form de pré-tournée.
 *   2. Extensions > Apps Script.
 *   3. Coller ce fichier (remplacer le contenu par défaut).
 *   4. Enregistrer, puis recharger la feuille : un menu "Osmoz Animae"
 *      apparaît en haut.
 *   5. Une fois les réponses reçues : menu "Osmoz Animae" > "Exporter en
 *      JSON" -> un fichier est créé dans Google Drive (dossier racine),
 *      nommé export_tournee_<date>.json. Le télécharger et le transmettre
 *      pour la Phase 2 (premier jet).
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Osmoz Animae')
    .addItem('Exporter en JSON', 'exportResponsesAsJson')
    .addToUi();
}

function exportResponsesAsJson() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) {
    SpreadsheetApp.getUi().alert('Aucune réponse trouvée sur cette feuille.');
    return;
  }

  const headers = data[0];
  const rows = data.slice(1);

  const responses = rows.map(function (row, i) {
    const obj = { _row: i + 2 }; // numéro de ligne réel dans la feuille, pour retrouver une réponse en cas de souci
    headers.forEach(function (header, j) {
      obj[header] = row[j];
    });
    return obj;
  });

  const json = JSON.stringify(responses, null, 2);

  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  const fileName = 'export_tournee_' + today + '.json';
  const file = DriveApp.createFile(fileName, json, MimeType.PLAIN_TEXT);

  SpreadsheetApp.getUi().alert(
    'Export terminé : ' + responses.length + ' réponse(s).\n\n' +
    'Fichier créé dans Google Drive : ' + fileName + '\n' +
    '(dossier racine "Mon Drive")\n\n' +
    'Lien direct : ' + file.getUrl()
  );
}
