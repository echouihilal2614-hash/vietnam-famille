"""Aperçu du « casting » : présentation des 4 membres de la famille façon film de braquage.
(Images provisoires : photo de Hilal + photos de lieux du site, en attendant les vraies vidéos.)"""
import sys, os, json
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE + '/outils')
from moteur import Projet, exporter_leger
IMG = os.path.join(os.path.dirname(RACINE), 'img') + '/'
EQ = json.load(open(RACINE + '/montages/equipe.json'))
b = 60 / 112; bar = 4 * b
P = Projet('casting', 1920, 1080, 30)
P.plan(type='ecran', couleur=(10, 10, 10), duree=bar + 0.1, look='neutre',
       textes=[dict(style='titre', t=0.1, d=bar - 0.15, txt='LE CASTING', taille=230, espacement=(2, 14), fad=(60, 120)),
               dict(style='sous_titre', t=0.4, d=bar - 0.45, txt='Việt Nam 2026 · l’équipe', y=700, taille=56)],
       sons=[dict(son='bip_rec', t=0.05, gain=-6), dict(son='clap_cinema', t=bar - 0.55, gain=-2)])
P.transition('flash', 0.2)
images = {'Hilal': ('hilal-sapa.jpg', (0.27, 0.73)), 'Ahmed': ('saigon-poste-4.jpg', (0.5, 0.5)),
          'Mounira': ('hoian-1.jpg', (0.5, 0.5)), 'Bochra': ('phuquoc-7.jpg', (0.5, 0.5))}
for k, qui in enumerate(['Hilal', 'Ahmed', 'Mounira', 'Bochra']):
    e = EQ[qui]; src, foc = images[qui]
    P.plan(type='photo', src=IMG + src, duree=2 * b + 0.1, zoom=(1.05, 1.18), focus=foc, courbe='in')
    P.transition('flash', 0.16, son='declic_photo', gain=-2)
    d = 2 * bar - 2 * b + (0.6 if k == 3 else 0)
    P.plan(type='photo', src=IMG + src, duree=d, nb=True, zoom=(1.2, 1.24), focus=foc, vignette=0.4,
           textes=[dict(style='perso', t=0.05, d=d - 0.15, nom=e['nom'], role=e['role'], details=e.get('details', []),
                        arabe=e.get('arabe'), translit=e.get('translit'), couleur=e['couleur'])],
           sons=[dict(son='whoosh', t=0.0, gain=-8)] + ([dict(son='ding', t=1.1, gain=-10)] if qui == 'Ahmed' else []))
    P.transition('whip_gauche' if k < 3 else 'fondu_noir', 0.3 if k < 3 else 0.6)
P.plan(type='ecran', couleur=(0, 0, 0), duree=1.0, look='neutre')
P.musique(RACINE + '/musique/vacances.wav', debut=0, offset=12 * bar - bar, gain=-1, fondu_out=1.2)
out = P.rendre(f'{P.dossier}/casting.mp4')
print(exporter_leger(out, out.replace('.mp4', '_telephone.mp4'), mbps=4.0))
