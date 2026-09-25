# Déployer le service de calcul (une seule fois)

Ce document explique comment mettre en ligne le moteur de tournée sur
Render, pour que Ludivine puisse déclencher un calcul depuis l'interface
(https://claude.ai/artifact/AsthzFog8bYKzfLbCyFMQ5) sans Terminal ni Python
installé. À faire **une seule fois** par Margaux (ou toute autre personne à
qui elle délègue) ; Ludivine n'a jamais besoin de refaire ces étapes.

Pourquoi Render : c'est l'option retenue le 25 sept. 2026 après vérification
de l'état réel des offres gratuites (voir `prototype-moteur-optimisation.md`
dans le projet Claude) -- gratuit tant que l'usage reste faible (quelques
calculs par mois), accès réseau sortant illimité (nécessaire pour appeler
OpenRouteService), support complet de Python/OR-Tools. Une carte bancaire
est demandée à l'inscription (vérification anti-fraude, ~1€, jamais
débitée tant qu'on reste dans le quota gratuit).

## 1. Créer un dépôt de code (GitHub)

Le code doit être quelque part que Render peut lire. Le plus simple sans
utiliser de ligne de commande :

1. Créer un compte sur https://github.com (gratuit, aucune carte requise).
2. Créer un nouveau dépôt (bouton vert "New") : nom au choix (ex.
   `osmoz-animae-tool`), visibilité **Private** (ce code traite des données
   clients, même s'il n'en stocke aucune -- autant rester prudent).
3. Sur la page du dépôt vide : lien "uploading an existing file" (ou "Add
   file > Upload files"). Glisser-déposer tout le contenu du dossier
   `OsmozAnimae` (celui qui contient déjà `engine/`, `interface/`,
   `bridge/`...) tel quel, **y compris** `render.yaml`, `.gitignore` et le
   dossier `engine/` en entier -- **sauf** `engine/.env` (ne jamais l'envoyer
   sur GitHub, même en dépôt privé : c'est le fichier qui contient la clé
   API) et `engine/.ors_cache.json`.
4. Valider ("Commit changes").

*(Si Margaux ou une autre personne préfère la ligne de commande : `git init`,
`git add .` puis `git commit` et `git push` font la même chose -- mais
l'upload par glisser-déposer suffit largement pour cette étape unique.)*

## 2. Créer le compte Render et connecter le dépôt

1. Aller sur https://render.com, "Get Started" -- s'inscrire avec le même
   compte GitHub (le plus simple) ou un email.
2. Renseigner une carte bancaire si demandé (vérification, pas de
   prélèvement tant que l'usage reste dans le quota gratuit -- voir plus
   haut).
3. Tableau de bord Render : "New +" > "Blueprint".
4. Sélectionner le dépôt GitHub créé à l'étape 1. Render détecte
   automatiquement `render.yaml` à la racine et propose de créer le service
   `osmoz-animae-moteur` déjà configuré (build/démarrage/dossier `engine/`).
5. Valider ("Apply" / "Create").

## 3. Renseigner les deux secrets

Render va demander les deux variables marquées `sync: false` dans
`render.yaml` (jamais commitées, à renseigner à la main) :

- `ORS_API_KEY` : la même clé OpenRouteService déjà utilisée dans
  `engine/.env` sur l'ordinateur de Margaux (menu Render du service >
  Environment > Add Environment Variable).
- `API_TOKEN` : un mot de passe simple inventé pour l'occasion (ex. une
  phrase aléatoire) -- c'est ce qui protège le service pour qu'un inconnu
  qui tomberait sur l'adresse ne puisse pas déclencher de calculs à volonté.
  À choisir une fois, puis à ne communiquer qu'à Ludivine (et à saisir dans
  les "Réglages de connexion" de l'interface, une fois, de son côté).

Après avoir renseigné les deux variables, Render redéploie automatiquement.

## 4. Récupérer l'adresse et finir la connexion

1. Sur le tableau de bord Render, la page du service affiche son adresse en
   haut, du type `https://osmoz-animae-moteur.onrender.com`.
2. Vérifier que ça répond : ouvrir `<cette adresse>/health` dans un
   navigateur -- doit afficher `{"status":"ok"}`.
3. Ouvrir l'interface (https://claude.ai/artifact/AsthzFog8bYKzfLbCyFMQ5),
   déplier "Réglages de connexion" et renseigner :
   - Adresse du service de calcul : l'adresse de l'étape 1.
   - Jeton d'accès : la valeur choisie pour `API_TOKEN` à l'étape 3.

C'est tout. Ludivine (ou Margaux) peut ensuite charger un export du
formulaire et cliquer "Calculer la tournée" directement depuis l'interface,
sans plus jamais ouvrir de Terminal. Ces réglages sont mémorisés par le
navigateur -- à refaire une fois par appareil (si Ludivine utilise son
propre ordinateur en plus de celui de Margaux, par exemple).

## À savoir pour la suite

- Le service gratuit Render se met en veille après 15 minutes sans usage :
  le premier calcul après une pause peut prendre jusqu'à une minute
  (l'interface l'indique). Les calculs suivants sont rapides.
- Aucune donnée client n'est stockée sur Render : chaque calcul est traité
  puis oublié (pas de base de données côté service).
- `run_tournee.py` et `recalculer_nuitees.py` (en ligne de commande, sur
  l'ordinateur de Margaux) restent utilisables comme filet de secours si le
  service Render est indisponible -- même logique, mêmes résultats (les
  deux chemins partagent `engine/tournee_service.py`).
