"""Planche sonore : chaque effet avec son nom à l'écran, pour choisir ses préférés."""
import sys, os
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE + '/outils')
import soundfile as sf
from moteur import Projet, exporter_leger
SONS = [
    ('declic_photo', 'Déclic photo', 'quand une photo apparaît'),
    ('rafale_photos', 'Rafale de photos', 'mode paparazzi'),
    ('flash', 'Flash', 'le flash se charge… et clac'),
    ('avance_pellicule', 'Pellicule', 'on avance la pellicule'),
    ('polaroid', 'Polaroid', 'la photo sort de l’appareil'),
    ('clap_cinema', 'Clap de cinéma', '« Action ! »'),
    ('bip_rec', 'Bip REC', 'le caméscope démarre'),
    ('projecteur_demarrage', 'Projecteur', 'le vieux film démarre'),
    ('projecteur_fond', 'Projecteur (fond)', 'ambiance film de famille'),
    ('vinyle_fond', 'Vinyle (fond)', 'ambiance souvenir'),
    ('rembobinage_vhs', 'Rembobinage VHS', 'retour en arrière'),
    ('tape_stop', 'Cassette qui s’arrête', 'fin brutale'),
    ('scratch', 'Disque rayé', 'moment gênant / arrêt sur image'),
    ('whoosh', 'Whoosh', 'transition rapide'),
    ('whoosh_long', 'Whoosh long', 'zoom à travers l’image'),
    ('glitch', 'Glitch', 'bug numérique'),
    ('riser', 'Montée', 'avant le gros moment'),
    ('impact', 'Impact', 'le gros moment'),
    ('pop', 'Pop', 'un texte apparaît'),
    ('ding', 'Ding', 'bonne idée / moment drôle'),
    ('boing', 'Boing', 'moment cartoon'),
]
P = Projet('planche_sonore', 1280, 720, 30)
fonds = [(40, 22, 14), (22, 30, 40), (30, 18, 36), (18, 34, 26)]
for k, (nom, titre, usage) in enumerate(SONS):
    a, sr = sf.read(f'{RACINE}/sons/{nom}.wav')
    long = nom.endswith('_fond')
    d = 3.2 if long else max(2.2, len(a) / sr + 0.9)
    i = P.plan(type='ecran', couleur=fonds[k % 4], duree=d, look='neutre',
               textes=[dict(style='titre', t=0.05, d=d - 0.1, txt=titre.upper(), taille=150, espacement=(2, 6), fad=(120, 150)),
                       dict(style='sous_titre', t=0.15, d=d - 0.2, txt=usage, y=470, taille=54, police='Montserrat Light'),
                       dict(style='sous_titre', t=0.05, d=d - 0.1, txt=f'{k + 1} / {len(SONS)}', y=640, taille=36)],
               sons=[] if long else [dict(son=nom, t=0.45, gain=0)])
    if long:
        t0 = P.debut(i); P.ambiance(nom, t0 + 0.2, t0 + d - 0.1, gain=0)
    P.transition('coupe')
out = P.rendre(f'{P.dossier}/planche_sonore.mp4')
print(exporter_leger(out, out.replace('.mp4', '_telephone.mp4'), mbps=1.0, hauteur=720))
