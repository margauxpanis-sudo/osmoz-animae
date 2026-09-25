/**
 * Création du vrai Google Form de pré-tournée — Osmoz Animae
 * ============================================================
 *
 * Crée en une fois le formulaire exact décrit dans pre-tournee-templates.md
 * (projet Claude), avec les intitulés de question EXACTS attendus par
 * engine/form_import.py (field_map par défaut) -- une seule lettre de
 * différence dans un intitulé casserait la lecture automatique des
 * réponses, donc ce script fixe les titres une bonne fois, à la main, au
 * lieu de les retaper dans l'interface de Google Forms.
 *
 * Ne remplace pas bridge/Code.gs : ce script-ci crée le formulaire ET sa
 * feuille de réponses (une fois, au début) ; Code.gs (à coller ensuite,
 * séparément, dans la feuille de réponses créée ici) sert lui à exporter
 * les réponses en JSON à chaque tournée. Deux scripts, deux moments.
 *
 * INSTALLATION (à faire une seule fois, par Margaux ou Ludivine) :
 *   1. Aller sur https://script.google.com -> "Nouveau projet".
 *   2. Effacer le contenu par défaut (myFunction vide) et coller ce fichier
 *      en entier à la place.
 *   3. En haut, sélectionner la fonction "creerFormulaireOsmozAnimae" dans
 *      le menu déroulant (à côté du bouton "Exécuter"), puis "Exécuter".
 *   4. Google demande une autorisation la première fois (c'est normal,
 *      c'est votre propre script qui a besoin d'accéder à Drive/Forms de
 *      votre propre compte) -- "Continuer" puis "Autoriser".
 *   5. Une fois l'exécution terminée : menu "Affichage" > "Journaux
 *      d'exécution" (ou Ctrl+Entrée / Cmd+Entrée). Trois liens y sont
 *      affichés :
 *        - le lien d'ÉDITION du formulaire (pour le personnaliser encore,
 *          ex. changer le [mois/saison] dans le titre, la date limite dans
 *          la description) ;
 *        - le lien PUBLIC à diffuser aux clients (celui du message
 *          WhatsApp d'envoi initial, voir pre-tournee-templates.md) ;
 *        - le lien de la feuille de réponses créée.
 *   6. ⚠️ Étape à ne pas sauter (déjà documentée, se reproduit à chaque
 *      nouveau formulaire) : ouvrir la feuille de réponses, sélectionner la
 *      colonne "Numéro de téléphone" > Format > Nombre > Texte brut --
 *      sinon Google Sheets convertit les numéros en nombre et supprime le
 *      0 initial (0601020304 devient 601020304).
 *   7. Dans la feuille de réponses : Extensions > Apps Script, coller le
 *      contenu de bridge/Code.gs (remplace le contenu par défaut),
 *      enregistrer, recharger la feuille -- le menu "Osmoz Animae" apparaît
 *      pour exporter les réponses en JSON le moment venu.
 */

function creerFormulaireOsmozAnimae() {
  var form = FormApp.create('Osmoz Animae — Préparation de la tournée [mois/saison]');
  form.setDescription(
    "Bonjour ! Pour organiser au mieux la prochaine tournée, merci de répondre à ce court " +
    "formulaire avant le [date limite]. Cela permet de caler les rendez-vous efficacement. Merci !"
  );
  form.setCollectEmail(false);

  // Intitulés EXACTS attendus par engine/form_import.py (default_map) --
  // ne pas reformuler, même légèrement.
  form.addTextItem()
    .setTitle('Nom et prénom')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Numéro de téléphone')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Lieu du rendez-vous')
    .setRequired(true);

  form.addTextItem()
    .setTitle("Nombre et type d'animaux à voir")
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('Jours possibles sur la période')
    .setChoiceValues(['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'])
    .setRequired(true);

  form.addTextItem()
    .setTitle("Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?")
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Remarques complémentaires')
    .setRequired(false);

  // Question 8, ajoutée le 25 sept. 2026 -- une seule case à cocher, jamais
  // obligatoire : une réponse absente est traitée comme "non abonné" côté
  // form_import.py (parse_abonnement), sans casser les tournées déjà en cours.
  form.addCheckboxItem()
    .setTitle('Abonnement annuel ?')
    .setChoiceValues(['Oui'])
    .setRequired(false);

  // Feuille de réponses -- créée ici plutôt que via le bouton "Créer une
  // feuille de calcul" de l'interface Forms, pour que tout se fasse en une
  // seule exécution.
  var ss = SpreadsheetApp.create('Osmoz Animae — Réponses tournée [mois/saison]');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  Logger.log('Formulaire créé.');
  Logger.log('Lien d\'édition (pour personnaliser le titre/la date limite) : ' + form.getEditUrl());
  Logger.log('Lien PUBLIC à diffuser aux clients : ' + form.getPublishedUrl());
  Logger.log('Feuille de réponses : ' + ss.getUrl());
  Logger.log('');
  Logger.log('⚠️ Étape suivante obligatoire : dans la feuille de réponses, mettre la colonne ' +
    '"Numéro de téléphone" en Format > Nombre > Texte brut (voir en-tête de ce fichier, étape 6).');
}
