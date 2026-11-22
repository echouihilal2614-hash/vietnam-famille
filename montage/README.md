# Atelier de montage — Việt Nam en famille

Outils pour monter le film des vacances (31 oct. → 12 nov. 2026) à partir des vidéos et photos de la famille.
Tout tourne avec `ffmpeg` + Python ; rien n'est envoyé sur Internet.

## Démarrer une session
```bash
./preparer.sh                      # environnement Python (.venv), sons et musiques provisoires (Mac : brew install ffmpeg avant)
python3 outils/analyse.py <rushes> <sortie>   # inventaire + planches contact + lieux (GPS) + pics sonores
python3 outils/rythme.py chanson.mp3          # tempo, temps, mesures (pour caler les coupes)
python3 outils/paroles.py <rushes> --sortie <dossier>   # ce qui se dit dans chaque vidéo, mot par mot
python3 montages/demo_style.py                # démo de style (photos du site)
```

## Ce qu'il y a dedans
| Fichier | Rôle |
|---|---|
| `outils/moteur.py` | Le moteur : plans vidéo/photo, polaroïds qui tombent, carte animée du trajet, rembobinage VHS, transitions (whip, zoom, glitch, flash, brûlure de pellicule…), textes animés, mixage audio avec ducking, export |
| `outils/analyse.py` | Trie les rushes : date, lieu le plus proche d'après le GPS, HDR, ralentis, planches contact pour visionner |
| `outils/rythme.py` | Analyse une musique : BPM, temps, premiers temps de mesure |
| `outils/paroles.py` | Transcrit ce qui se dit dans les vidéos (mot par mot, minuté) : repère les phrases cultes et alimente les sous-titres façon TikTok. Le modèle se télécharge depuis huggingface.co |
| `outils/sons.py` | Effets sonores synthétisés (whoosh, scratch, déclic photo, rembobinage VHS, vinyle…) |
| `outils/musique.py` | Deux musiques provisoires libres de droits (« vacances » 112 BPM, « nostalgie » 72 BPM) |
| `montages/*.py` | Les montages eux-mêmes (une liste de plans calés sur la musique) |
| `fonts/` | Polices Google Fonts (licence OFL), avec les accents vietnamiens |
| `carte.json` | Contour du pays (Natural Earth) et étapes du voyage, repris du site |

## Les looks
- **vacances** : couleurs vives, contraste, ombres turquoise et hautes lumières chaudes
- **nostalgie** : couleurs adoucies, noirs délavés, teinte chaude, grain, vignettage, léger tremblement de pellicule
- **nb** : noir et blanc (arrêts sur image)

## Effets disponibles dans un plan
- `son` (volume du son du rush) et `duck` (baisse de la musique en dB pendant le plan, 40 = coupée) : pour garder les moments drôles et les phrases cultes
- texte `paroles` : sous-titres façon TikTok, le mot prononcé surligné en jaune
- `gel=(t, durée, 'nb')` + texte `perso` : arrêt sur image en noir et blanc avec présentation d'un personnage
- `punch` (zoom rapide sur un détail), `secousse`, `vitesse`, `inverse`, `cinema` (bandes noires), `zoom`/`focus` (mouvement de caméra)
- transitions : `whip_*`, `zoom`, `glitch`, `flash`, `brulure`, `fondu`, `fondu_noir`, `rideau`
- plans spéciaux : `pile` (polaroïds qui tombent), `carte` (trajet animé), `rembobinage` (VHS), `ecran` (titre)
