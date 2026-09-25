/**
 * Pont interface -> Google Agenda — Osmoz Animae
 * =================================================
 *
 * Reçoit la tournée VALIDÉE (relue dans revue_tournee.html) et crée un
 * événement par arrêt sur l'agenda par défaut du compte Google sur lequel
 * ce script est déployé (celui de Ludivine). Même esprit que bridge/Code.gs :
 * ce script ne décide rien, il exécute tel quel ce que l'interface lui
 * envoie -- toute la logique (qui va où, quel jour, quelle heure) a déjà
 * été calculée et relue avant d'arriver ici.
 *
 * Pourquoi Apps Script plutôt qu'une vraie API Google Calendar depuis le
 * service Render : CalendarApp est déjà autorisé sur le compte de Ludivine
 * sans configuration OAuth/Google Cloud Console à monter -- même principe
 * que bridge/Code.gs et creer_formulaire_osmoz_animae.gs, pas de nouvelle
 * brique d'infrastructure.
 *
 * SÉCURITÉ : ce script est déployé en accès "Tout le monde" (obligatoire
 * pour qu'un navigateur puisse l'appeler sans compte Google), donc protégé
 * par un jeton simple vérifié ci-dessous -- change AGENDA_TOKEN avant de
 * déployer, et renseigne la même valeur dans l'interface (Réglages de
 * connexion > Jeton de l'agenda). Ne protège pas d'un attaquant déterminé,
 * juste d'un inconnu qui tomberait sur l'URL -- proportionné à un usage à
 * une seule utilisatrice, même logique que API_TOKEN côté Render.
 *
 * ANTI-DOUBLON : chaque événement porte une marque invisible dans sa
 * description ([osmoz:stop_id:day_index]). Avant de créer un événement, le
 * script vérifie qu'aucun événement avec la même marque n'existe déjà sur
 * le créneau visé -- cliquer deux fois sur "Envoyer sur l'agenda" (après un
 * recalcul suite à une nuitée, par exemple) ne duplique donc pas les
 * événements déjà posés, mais les recrée avec les nouveaux horaires si le
 * créneau a changé (l'ancien événement, à l'ancien horaire, n'est PAS
 * supprimé automatiquement -- à faire à la main si besoin, pour ne jamais
 * supprimer un événement sans que quelqu'un l'ait décidé).
 *
 * INSTALLATION (à faire une seule fois, par Margaux ou Ludivine) :
 *   1. Changer la valeur d'AGENDA_TOKEN ci-dessous (n'importe quelle phrase,
 *      gardée secrète) AVANT l'étape suivante.
 *   2. Aller sur https://script.google.com -> "Nouveau projet" (sur le
 *      compte Google de Ludivine -- c'est SON agenda qui recevra les
 *      événements).
 *   3. Effacer le contenu par défaut, coller ce fichier en entier.
 *   4. Enregistrer (icône disquette, ou Ctrl/Cmd+S).
 *   5. En haut à droite : "Déployer" > "Nouveau déploiement".
 *   6. Cliquer l'icône en forme d'engrenage à côté de "Sélectionner le
 *      type", choisir "Application Web".
 *   7. Réglages : "Exécuter en tant que" = Moi ; "Qui a accès" = Tout le
 *      monde. Cliquer "Déployer".
 *   8. Google demande une autorisation (accès à l'agenda du compte) --
 *      "Continuer" puis "Autoriser", comme pour le script du formulaire.
 *   9. Copier l'URL affichée ("URL de l'application Web", se termine par
 *      /exec) -- c'est l'"Adresse de l'agenda" à coller dans l'interface
 *      (Réglages de connexion), avec le jeton choisi à l'étape 1.
 *  10. Pour une future modification de ce script : "Déployer" >
 *      "Gérer les déploiements" > icône crayon > "Nouvelle version" --
 *      garde la même URL. Créer un "Nouveau déploiement" en changerait
 *      l'adresse (à éviter, sauf besoin explicite).
 */

var AGENDA_TOKEN = 'change-moi-avant-de-deployer';

function doPost(e) {
  var result = { created: 0, skipped: 0, errors: [] };
  var payload;

  try {
    payload = JSON.parse(e.postData.contents);
  } catch (err) {
    return jsonOutput_({ error: "Corps de requête illisible (JSON invalide)." });
  }

  if (!payload || payload.token !== AGENDA_TOKEN) {
    return jsonOutput_({ error: "Jeton invalide." });
  }

  var evenements = payload.evenements || [];
  var calendar = CalendarApp.getDefaultCalendar();

  evenements.forEach(function (ev) {
    try {
      var start = new Date(ev.annee, ev.mois - 1, ev.jour, Math.floor(ev.debut_min / 60), ev.debut_min % 60);
      var end = new Date(ev.annee, ev.mois - 1, ev.jour, Math.floor(ev.fin_min / 60), ev.fin_min % 60);
      var marque = '[osmoz:' + ev.stop_id + ':' + ev.day_index + ']';

      // Anti-doublon : ne recrée pas un événement déjà posé pour ce
      // stop_id+jour sur EXACTEMENT ce créneau (voir note en tête de fichier
      // si le créneau a changé entre deux envois).
      var existants = calendar.getEvents(start, end);
      var dejaPresent = existants.some(function (existing) {
        return (existing.getDescription() || '').indexOf(marque) !== -1;
      });
      if (dejaPresent) {
        result.skipped++;
        return;
      }

      var description = [
        ev.animaux ? ('Animaux : ' + ev.animaux) : null,
        ev.telephone ? ('Téléphone : ' + ev.telephone) : null,
        ev.notes ? ('Remarques : ' + ev.notes) : null,
        ev.abonnement_annuel ? '⭐ Abonnement annuel' : null,
        marque,
      ].filter(function (x) { return x; }).join('\n');

      calendar.createEvent(ev.titre, start, end, {
        location: ev.lieu || '',
        description: description,
      });
      result.created++;
    } catch (err) {
      result.errors.push((ev.titre || ev.stop_id || '?') + ' : ' + err.message);
    }
  });

  return jsonOutput_(result);
}

function jsonOutput_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
