"""Démo de style (avec les photos du site, en attendant les vrais rushes).
Partie 1 « vacances » calée sur la musique (112 BPM) -> gag -> rembobinage VHS -> partie 2 « nostalgie » (72 BPM)."""
import sys, os
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE + '/outils')
from moteur import Projet
IMG = os.path.join(os.path.dirname(RACINE), 'img') + '/'   # photos du site (dossier img/ du dépôt)
M = RACINE + '/musique/'
P = Projet('demo_style', 1920, 1080, 30)
b = 60 / 112; bar = 4 * b          # partie 1
OFF = 6 * bar                        # on démarre la musique à la mesure 6 (fin de l'intro)

def seq(items, t0, d0=0.0):
    """items = [(plan_dict, fin_coupe, transition, duree_trans)] ; calcule les durées pour que
    chaque transition soit centrée sur sa coupe (calée sur le temps musical)."""
    prev_cut, prev_d = t0, d0
    for p, cut, tr, d in items:
        p['duree'] = (cut + d / 2) - (prev_cut - prev_d / 2)
        P.plan(**p); P.transition(tr, d)
        prev_cut, prev_d = cut, d
    return prev_cut

T = lambda beats: beats * b          # temps de la timeline (partie 1)
punch = lambda: dict(zoom=(1.0, 1.10), courbe='out')
items = [
    (dict(type='ecran', couleur=(8, 8, 8), textes=[dict(style='sous_titre', t=0.35, d=1.9, txt='AHMED · MOUNIRA · BOCHRA · HILAL', y=540, taille=58)]),
     T(4), 'fondu', 0.6),
    (dict(type='photo', src=IMG + 'hanoi-lac-0.jpg', zoom=(1.0, 1.15)), T(8), 'whip_gauche', 0.35),
    # montée : coupes toutes les 2 temps, puis à chaque temps
    (dict(type='photo', src=IMG + 'hanoi-rue-1.jpg', **punch()), T(10), 'coupe', 0),
    (dict(type='photo', src=IMG + 'hanoi-encens-0.jpg', zoom=(1.15, 1.0), courbe='out'), T(12), 'glitch', 0.2),
    (dict(type='photo', src=IMG + 'temple-0.jpg', **punch()), T(14), 'whip_haut', 0.3),
    (dict(type='photo', src=IMG + 'sapa-3.jpg', zoom=(1.0, 1.12), focus=(0.3, 0.5), focus_fin=(0.7, 0.5)), T(16), 'coupe', 0),
    (dict(type='photo', src=IMG + 'ninhbinh-3.jpg', **punch()), T(17), 'coupe', 0),
    (dict(type='photo', src=IMG + 'hoian-1.jpg', **punch()), T(18), 'coupe', 0),
    (dict(type='photo', src=IMG + 'bana-0.jpg', **punch()), T(19), 'glitch', 0.16),
    (dict(type='photo', src=IMG + 'saigon-6.jpg', **punch()), T(20), 'coupe', 0),
    (dict(type='photo', src=IMG + 'mekong-0.jpg', **punch()), T(21), 'coupe', 0),
    (dict(type='photo', src=IMG + 'phuquoc-7.jpg', **punch()), T(22), 'coupe', 0),
    (dict(type='photo', src=IMG + 'honthom-6.jpg', **punch()), T(23), 'coupe', 0),
    (dict(type='photo', src=IMG + 'saigon-poste-4.jpg', zoom=(1.0, 1.25), courbe='in'), T(24), 'flash', 0.3),
    # DROP
    (dict(type='photo', src=IMG + 'halong-3.jpg', zoom=(1.18, 1.0), courbe='out',
          textes=[dict(style='titre', t=0.12, d=3.9, txt='VIỆT NAM', taille=360, fad=(80, 400)),
                  dict(style='sous_titre', t=0.6, d=3.4, txt='31 OCTOBRE — 12 NOVEMBRE 2026', y=735, taille=58)],
          sons=[dict(son='impact', t=0.0, gain=-1)]), T(32), 'zoom', 0.5),
    (dict(type='carte', de='hanoi', a='lanha', visites=['hanoi'], look='neutre'), T(40), 'whip_haut', 0.35),
    (dict(type='photo', src=IMG + 'lanha-7.jpg', zoom=(1.0, 1.12), focus=(0.4, 0.5), focus_fin=(0.6, 0.5),
          textes=[dict(style='lieu', t=0.4, d=3.4, nom='Lan Hạ', sous="UNE NUIT SUR L'EAU")]), T(48), 'coupe', 0),
    # GAG
    (dict(type='ecran', couleur=(8, 8, 8),
          textes=[dict(style='sous_titre', t=0.1, d=2.0, txt='Le programme officiel :', y=440, taille=66),
                  dict(style='titre', t=0.45, d=1.65, txt='« AUCUNE RANDONNÉE »', taille=200, y=590, espacement=(2, 6), fad=(120, 0))]),
     T(52), 'coupe', 0),
]
fin1 = seq(items, 0)
gag_t = fin1
P.plan(type='photo', src=IMG + 'hilal-sapa.jpg', duree=3.3, zoom=(1.0, 1.0), focus=(0.5, 0.62),
       punch=[(1.55, 1.55, (0.26, 0.74), 9)], secousse=[(1.55, 14, 0.35)],
       textes=[dict(style='meme', t=0.05, d=3.2, txt='Hilal, 2 heures plus tard :', pos='haut')],
       sons=[dict(son='scratch', t=-0.04, gain=0), dict(son='pop', t=0.06, gain=-6), dict(son='boing', t=1.55, gain=-4)])
P.transition('coupe')
P.musique(M + 'vacances.wav', debut=0, offset=OFF, fin=gag_t + 0.02, fondu_in=0.8, fondu_out=0.04)
# REMBOBINAGE -> NOSTALGIE
rew_i = P.plan(type='rembobinage', plans=list(range(2, 17)), duree=2.6, look='neutre',
               textes=[dict(style='vhs_osd', t=0, d=2.6, haut='REW', rew=True)],
               sons=[dict(son='rembobinage_vhs', t=0, gain=-3), dict(son='tape_stop', t=2.0, gain=-8)])
P.transition('brulure', 1.0)
T2 = P.debut(rew_i) + 2.6 - 0.5         # milieu de la brûlure = début de la partie 2
nb = 60 / 72; nbar = 4 * nb
items2 = [
    (dict(type='photo', src=IMG + 'ninhbinh-0.jpg', look='nostalgie', zoom=(1.0, 1.1),
          textes=[dict(style='vhs_osd', t=0.3, d=3.0, haut='PLAY', date_txt='NOV. 2026'),
                  dict(style='manuscrit', t=2.2, d=4.6, txt="Ce qu'on ne veut pas oublier…", y=880)]),
     T2 + 2 * nbar, 'brulure', 1.0),
    (dict(type='pile', look='nostalgie', intervalle=2 * nb, photos=[
        dict(src=IMG + 'hoian-1.jpg', legende='Hội An, les lanternes', t=0.6),
        dict(src=IMG + 'mekong-0.jpg', legende='Le marché flottant', t=0.6 + 2 * nb),
        dict(src=IMG + 'saigon-poste-4.jpg', legende='La poste de Saigon', t=0.6 + 4 * nb),
        dict(src=IMG + 'honthom-6.jpg', legende='Le téléphérique de Hòn Thơm', t=0.6 + 6 * nb),
        dict(src=IMG + 'phuquoc-7.jpg', legende='Phú Quốc', t=0.6 + 8 * nb),
        dict(src=IMG + 'bana-0.jpg', legende="Le Pont d'Or", t=0.6 + 10 * nb)],
        sons=[dict(son='declic_photo', t=0.6 + k * 2 * nb + 0.38, gain=-12) for k in range(6)]),
     T2 + 6 * nbar, 'fondu', 1.0),
    (dict(type='photo', src=IMG + 'hanoi-encens-0.jpg', look='nostalgie', zoom=(1.12, 1.0), focus=(0.55, 0.3),
          textes=[dict(style='manuscrit', t=1.0, d=5.0, txt='Hà Nội, là où tout a commencé', y=900)]),
     T2 + 8 * nbar, 'fondu', 1.2),
    (dict(type='photo', src=IMG + 'sapa-3.jpg', look='nostalgie', zoom=(1.15, 1.0), courbe='out',
          textes=[dict(style='manuscrit', t=3.0, d=6.0, txt='On reviendra.', taille=190)]),
     T2 + 11 * nbar, 'fondu_noir', 1.6),
]
fin2 = seq(items2, T2, d0=1.0)
P.plan(type='ecran', couleur=(8, 8, 8), duree=7.5,
       textes=[dict(style='titre', t=0.6, d=6.2, txt='VIỆT NAM', taille=190, couleur='D8E8F5', espacement=(10, 22)),
               dict(style='sous_titre', t=1.2, d=5.6, txt='AHMED · MOUNIRA · BOCHRA · HILAL', y=665, taille=50),
               dict(style='sous_titre', t=1.8, d=5.0, txt='novembre 2026', y=745, taille=44, police='Montserrat Light')])
P.musique(M + 'nostalgie.wav', debut=T2 - 0.3, fondu_in=0.6, fondu_out=4.0, gain=-3)
P.ambiance('vinyle_fond', T2, P.duree_totale() - 0.5, gain=-16)
print('durée totale', round(P.duree_totale(), 2), 's ;', len(P.plans), 'plans')
apercu = '--apercu' in sys.argv
from moteur import exporter_leger, remixer
out = f'{P.dossier}/demo_style{"_apercu" if apercu else ""}.mp4'
if '--audio' in sys.argv:      # ne refait que le son
    remixer(P, out)
else:
    P.rendre(out, apercu=apercu)
print(exporter_leger(out, out.replace('.mp4', '_telephone.mp4'), mbps=4.0))
