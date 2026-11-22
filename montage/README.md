# Atelier de montage — Việt Nam en famille

Outils pour monter le film des vacances (31 oct. → 12 nov. 2026) à partir des vidéos et photos de la famille.
Tout tourne avec `ffmpeg` + Python ; rien n'est envoyé sur Internet.

## Démarrer une session
```bash
./preparer.sh                      # bibliothèques, polices, sons et musiques provisoires
python3 outils/analyse.py <rushes> <sortie>   # inventaire + planches contact + lieux (GPS) + pics sonores
python3 outils/rythme.py chanson.mp3          # tempo, temps, mesures (pour caler les coupes)
python3 montages/demo_style.py                # démo de style (photos du site)
```

## Ce qu'il y a dedans
| Fichier | Rôle |
|---|---|
| `outils/moteur.py` | Le moteur : plans vidéo/photo, polaroïds qui tombent, carte animée du trajet, rembobinage VHS, transitions (whip, zoom, glitch, flash, brûlure de pellicule…), textes animés, mixage audio avec ducking, export |
| `outils/analyse.py` | Trie les rushes : date, lieu le plus proche d'après le GPS, HDR, ralentis, planches contact pour visionner |
| `outils/rythme.py` | Analyse une musique : BPM, temps, premiers temps de mesure |
| `outils/sons.py` | Effets sonores synthétisés (whoosh, scratch, déclic photo, rembobinage VHS, vinyle…) |
| `outils/musique.py` | Deux musiques provisoires libres de droits (« vacances » 112 BPM, « nostalgie » 72 BPM) |
| `montages/*.py` | Les montages eux-mêmes (une liste de plans calés sur la musique) |
| `fonts/` | Polices Google Fonts (licence OFL), avec les accents vietnamiens |
| `carte.json` | Contour du pays (Natural Earth) et étapes du voyage, repris du site |

## Les looks
- **vacances** : couleurs vives, contraste, ombres turquoise et hautes lumières chaudes
- **nostalgie** : couleurs adoucies, noirs délavés, teinte chaude, grain, vignettage, léger tremblement de pellicule
- **nb** : noir et blanc (arrêts sur image)
