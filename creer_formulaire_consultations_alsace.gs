/**
 * Création du Google Form mensuel — mode "consultations" Alsace, Osmoz Animae
 * ==============================================================================
 *
 * Distinct de bridge/creer_formulaire_osmoz_animae.gs (tournées bretonnes
 * classiques, jours de semaine cochés) : ce formulaire-ci sert au nouvel axe
 * décrit par Ludivine à Margaux le 26 sept. 2026 -- consultations régulières
 * en Alsace, partagées une fois par MOIS entier (décision actée le même
 * jour : calcul mensuel en un seul bloc, pas par quinzaine -- voir
 * prototype-moteur-optimisation.md, section "Bascule quinzaine → mois").
 *
 * Différence clé avec le formulaire classique : la question "Jours possibles
 * sur la période" (cases Lundi/Mardi/.../Dimanche) devient "Dates possibles
 * sur la période" (cases DD/MM précises, une par jour du mois) -- exigé côté
 * moteur car un mois contient presque toujours 4 lundis, 4 mardis, etc., ce
 * qui rendrait le mécanisme par nom de jour de semaine ambigu pour quasiment
 * chaque cliente (voir engine/form_import.map_dates, construit exactement
 * pour ce cas). Intitulé EXACT attendu côté moteur quand format_dispo=
 * "dates_precises" -- ne pas reformuler, même légèrement.
 *
 * INSTALLATION ET RÉEXÉCUTION MENSUELLE :
 *   1. Modifier les 6 variables juste en dessous (année/mois/jour de début,
 *      nombre de jours, jours fermés récurrents, dates fermées ponctuelles)
 *      pour le mois à venir.
 *   2. https://script.google.com -> "Nouveau projet" la première fois (les
 *      mois suivants : rouvrir ce même projet et juste modifier les
 *      variables puis ré-exécuter -- ça crée un NOUVEAU formulaire à chaque
 *      exécution, un par mois, jamais le même formulaire réutilisé).
 *   3. Sélectionner "creerFormulaireConsultationsAlsace" dans le menu
 *      déroulant en haut, puis "Exécuter". Autorisation Google demandée la
 *      première fois seulement (normal, c'est votre propre script sur votre
 *      propre compte).
 *   4. "Affichage" > "Journaux d'exécution" (Ctrl/Cmd+Entrée) : trois liens
 *      (édition du formulaire, lien public à diffuser, feuille de réponses).
 *   5. ⚠️ Comme pour le formulaire classique : dans la feuille de réponses,
 *      colonne "Numéro de téléphone" > Format > Nombre > Texte brut (sinon
 *      le 0 initial du téléphone disparaît).
 *   6. Dans la feuille de réponses : Extensions > Apps Script, coller
 *      bridge/Code.gs (identique au formulaire classique, pas besoin d'une
 *      version différente), enregistrer, recharger -- menu "Osmoz Animae"
 *      pour exporter les réponses en JSON le moment venu.
 *   7. Au moment du calcul dans revue_tournee.html ("Réglage avancé") :
 *      choisir "dates précises" dans "Format des disponibilités", et
 *      renseigner la date de début + le nombre de jours -- affichés dans les
 *      journaux d'exécution à l'étape 4 pour éviter toute ressaisie erronée.
 */

// ---- À MODIFIER CHAQUE MOIS, avant d'exécuter ------------------------------
var START_YEAR = 2026;
var START_MONTH = 10; // 1 = janvier ... 12 = décembre
var START_DAY = 1;
var NUM_DAYS = 31; // couvre le mois entier -- l'API du moteur accepte jusqu'à 31 jours

// Jours de la semaine où Ludivine ne travaille JAMAIS en Alsace (optionnel).
// Si renseigné, ces dates ne sont même pas proposées comme option de case à
// cocher -- évite qu'une cliente choisisse une date d'avance perdue.
// Laisser [] si aucun jour fixe n'est fermé (les fermetures seront alors
// gérées uniquement au moment du calcul, via jours_exclus/dates_fermees dans
// l'interface -- une cliente pourrait alors cocher une date qui se révèle
// fermée après coup, avec un avertissement nommé pour Ludivine, pas un plantage).
// Exemple : ['Dimanche']
var JOURS_FERMES = [];

// Dates ponctuelles déjà connues comme fermées ce mois-ci (congés, jour
// férié...), format 'AAAA-MM-JJ'. Laisser [] si aucune connue à l'avance.
// Exemple : ['2026-10-14']
var DATES_FERMEES = [];
// -----------------------------------------------------------------------------

function creerFormulaireConsultationsAlsace() {
  var dates = _datesDuMois();
  if (dates.length === 0) {
    throw new Error('Aucune date à proposer -- vérifie JOURS_FERMES / DATES_FERMEES, tout semble exclu.');
  }

  var moisNoms = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
    'août', 'septembre', 'octobre', 'novembre', 'décembre'];
  var libelleMois = moisNoms[START_MONTH - 1] + ' ' + START_YEAR;

  var form = FormApp.create('Osmoz Animae — Consultations Alsace — ' + libelleMois);
  form.setDescription(
    'Bonjour ! Pour organiser les consultations du mois de ' + libelleMois + ' en Alsace, ' +
    'merci de cocher TOUTES les dates qui vous conviennent (plusieurs choix possibles) et de ' +
    'répondre aux quelques questions ci-dessous. Merci !'
  );
  form.setCollectEmail(false);

  // Intitulés EXACTS attendus par engine/form_import.py / tournee_service.py
  // -- identiques au formulaire classique, sauf la question dates ci-dessous.
  form.addTextItem().setTitle('Nom et prénom').setRequired(true);
  form.addTextItem().setTitle('Numéro de téléphone').setRequired(true);
  form.addTextItem().setTitle('Lieu du rendez-vous').setRequired(true);
  form.addTextItem().setTitle("Nombre et type d'animaux à voir").setRequired(true);

  // Intitulé EXACT attendu quand format_dispo="dates_precises"
  // (tournee_service._JOURS_FIELD_BY_FORMAT) -- ne pas reformuler.
  form.addCheckboxItem()
    .setTitle('Dates possibles sur la période')
    .setChoiceValues(dates)
    .setRequired(true);

  form.addTextItem()
    .setTitle("Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?")
    .setRequired(true);

  form.addParagraphTextItem().setTitle('Remarques complémentaires').setRequired(false);

  // Même logique que le formulaire classique : jamais obligatoire, une
  // réponse absente vaut "non abonné" côté parse_abonnement, sans casser
  // les formulaires déjà diffusés.
  form.addCheckboxItem()
    .setTitle('Abonnement annuel ?')
    .setChoiceValues(['Oui'])
    .setRequired(false);

  var ss = SpreadsheetApp.create('Osmoz Animae — Réponses consultations Alsace — ' + libelleMois);
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  var debutAffiche = Utilities.formatDate(
    new Date(START_YEAR, START_MONTH - 1, START_DAY), Session.getScriptTimeZone(), 'dd/MM/yyyy');

  Logger.log('Formulaire créé pour ' + libelleMois + ' (' + dates.length + ' dates proposées sur ' + NUM_DAYS + ' jours).');
  Logger.log("Lien d'édition (pour personnaliser) : " + form.getEditUrl());
  Logger.log('Lien PUBLIC à diffuser aux clientes : ' + form.getPublishedUrl());
  Logger.log('Feuille de réponses : ' + ss.getUrl());
  Logger.log('');
  Logger.log('⚠️ Étape suivante obligatoire : dans la feuille de réponses, colonne "Numéro de ' +
    'téléphone" > Format > Nombre > Texte brut.');
  Logger.log('');
  Logger.log('Côté calcul (revue_tournee.html > "Réglage avancé") : "Format des disponibilités" = ' +
    '"dates précises", début = ' + debutAffiche + ', jours = ' + NUM_DAYS + '.');
}

function _datesDuMois() {
  var joursFermesNorm = JOURS_FERMES.map(function(j) { return j.trim().toLowerCase(); });
  var datesFermeesSet = {};
  DATES_FERMEES.forEach(function(d) { datesFermeesSet[d] = true; });

  // getDay() : 0=dimanche ... 6=samedi (JavaScript, pas Python) -- tableaux
  // alignés sur cet ordre, pas sur _WEEKDAYS_FR (Python, 0=lundi).
  var nomsJours = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
  var nomsJoursMaj = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];

  var result = [];
  var d = new Date(START_YEAR, START_MONTH - 1, START_DAY);
  for (var i = 0; i < NUM_DAYS; i++) {
    var jourSemaine = nomsJours[d.getDay()];
    var isoDate = Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    var estFerme = joursFermesNorm.indexOf(jourSemaine) !== -1 || !!datesFermeesSet[isoDate];
    if (!estFerme) {
      var ddmm = Utilities.formatDate(d, Session.getScriptTimeZone(), 'dd/MM');
      // Format "Lundi 05/10" -- le nom du jour aide la cliente à s'y
      // retrouver visuellement ; le moteur (map_dates) ne lit que le DD/MM
      // via une expression régulière, le nom du jour est ignoré sans risque.
      result.push(nomsJoursMaj[d.getDay()] + ' ' + ddmm);
    }
    d.setDate(d.getDate() + 1);
  }
  return result;
}
