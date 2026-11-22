# Notes du montage (souhaits de Hilal)

## Style
- Montage très stylé : effets spéciaux, transitions, bruitages (photo, tournage, clavier…).
- Début drôle et stylé, fin nostalgique avec les photos (polaroïds).
- Garder le vrai son des vidéos quand c'est drôle (ex. dans l'avion : « Welcome to Qatar »), musique baissée ou coupée, sous-titres façon TikTok.

## Intro « Mood ON » (exemple TikTok envoyé par Hilal)
- Le bouton **mode avion** s'allume sur le téléphone, zoom sur l'icône d'avion -> raccord sur un **vrai avion dans le ciel** (même forme, même place).
- Puis la journée de voyage en coupes rapides calées sur le rythme (~0,8 s, ~108 BPM) : couloir d'aéroport, avion derrière la vitre,
  tableau des départs, panneaux des portes, tapis roulant, escalator, écran du siège avec la carte du vol, « Welcome to Qatar ».
- Rushes utiles : enregistrement d'écran du mode avion (ou animation faite par l'atelier), un avion vu du sol / décollage / hublot.

## Musiques
- Début : un son TikTok classique de voyage, sans gros mot (proposé : « See Tình » – Hoàng Thùy Linh).
- Fin (nostalgie) : chanson évoquée comme « ala la taloumani » (titre exact à confirmer avec Hilal, ou MP3 fourni).

## Casting (présentation des personnages)
- Sur des vidéos précises choisies par Hilal : arrêt sur image sur chacun.
- Le NOM et le RÔLE s'écrivent au clavier, lettre par lettre, avec le bruit des touches (à faire avec les vraies vidéos).
- Rôles : voir `equipe.json` (Ahmed = وزير المالية, ministre des finances).

## Fichiers
- Vidéos/photos : sur le Mac de Hilal (dossier partagé via Remote Control) ; dépôt privé `vietnam-montage` pour les petits fichiers.
- Format (horizontal / vertical) : à confirmer.

## Où on en est (22 nov. 2026, soir)
- Fait : moteur de montage, démo de style, planche sonore, casting (rôles tapés au clavier), transcription des paroles,
  sous-titres TikTok, arrêt sur image + fiche personnage, bandes cinéma.
- Les rushes sont sur le Mac de Hilal dans `~/Documents/Vietnam` (pas accessibles depuis une session cloud) :
  le montage continue dans une session Claude Code qui tourne sur le Mac.
- Prochaines étapes :
  1. `preparer.sh`, puis `outils/analyse.py ~/Documents/Vietnam <sortie>` et `outils/paroles.py ~/Documents/Vietnam --sortie <sortie>`.
  2. Regarder les planches contact + paroles.md, repérer les moments drôles (« Welcome to Qatar »), les vidéos d'aéroport/avion.
  3. Demander à Hilal : format (horizontal/vertical), MP3 des musiques, vidéo/moment précis pour figer chaque personne du casting.
  4. Monter : intro mode avion -> départ en coupes rapides -> « Welcome to Qatar » -> titre VIỆT NAM -> casting (nom + rôle tapés au clavier)
     -> voyage (lieux, carte, gags avec le vrai son) -> rembobinage VHS -> partie nostalgie (polaroïds, musique nostalgique) -> générique.
  5. Exporter une version avec musique (famille/WhatsApp) et une sans musique (TikTok/Insta).
