"""Analyse d'une musique : tempo, temps, premiers temps de mesure, sections et « drop ».
Usage : python3 rythme.py chanson.mp3  ->  chanson.rythme.json (+ résumé à l'écran)
Le montage s'en sert pour caler les coupes et les transitions sur la musique."""
import sys, json, subprocess
import numpy as np, librosa

def charger(path, sr=22050):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True)
    return np.frombuffer(r.stdout, np.float32), sr

def analyser(path):
    y, sr = charger(path)
    hop = 512
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop, units='frames')
    tempo = float(np.atleast_1d(tempo)[0])
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=hop)
    # recalage : le traqueur peut se caler sur les contretemps -> on cherche le décalage
    # (± un demi-temps) qui aligne le mieux la grille sur les attaques graves (grosse caisse, basse)
    low_on = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, fmax=200, n_mels=32)
    tb = 60 / tempo; best, best_s = 0.0, -1
    for off in np.arange(-tb / 2, tb / 2, 0.01):
        idx = librosa.time_to_frames(bt + off, sr=sr, hop_length=hop)
        idx = idx[(idx >= 0) & (idx < len(low_on))]
        sc = low_on[idx].mean() if len(idx) else 0
        if sc > best_s: best, best_s = off, sc
    bt = bt + best; bt = bt[bt >= 0]
    beats = librosa.time_to_frames(bt, sr=sr, hop_length=hop)
    # premier temps de la mesure : la phase (0..3) dont les temps ont le plus de basses
    S = np.abs(librosa.stft(y, hop_length=hop, n_fft=2048))
    low = S[:int(150 / (sr / 2048))].sum(0)
    lowb = low[np.clip(beats, 0, len(low) - 1)]
    # sync() ajoute un segment [0, 1er temps] en tête : on l'enlève pour que la colonne k = segment qui COMMENCE au temps k
    chb = librosa.util.sync(librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop), beats, aggregate=np.median)[:, 1:]
    nov = np.r_[0, np.linalg.norm(np.diff(chb, axis=1), axis=0)][:len(beats)]   # changement d'accord à chaque temps
    sc_low = np.array([lowb[k::4].mean() if len(lowb[k::4]) else 0 for k in range(4)]); sc_low /= sc_low.max() + 1e-9
    sc_ch = np.array([nov[k::4].mean() if len(nov[k::4]) else 0 for k in range(4)]); sc_ch /= sc_ch.max() + 1e-9
    phase = int(np.argmax(sc_low + 1.5 * sc_ch))
    downs = bt[phase::4]
    # énergie (RMS) lissée par mesure -> sections et drop
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    t_rms = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    e_bar = [float(rms[(t_rms >= a) & (t_rms < b)].mean()) if b > a else 0 for a, b in zip(downs[:-1], downs[1:])]
    e = np.array(e_bar); drops = []
    lowe = [float(low[(librosa.frames_to_time(np.arange(len(low)), sr=sr, hop_length=hop) >= a) &
                      (librosa.frames_to_time(np.arange(len(low)), sr=sr, hop_length=hop) < b)].mean()) if b > a else 0
            for a, b in zip(downs[:-1], downs[1:])]
    le = np.array(lowe)
    if len(le) > 4:
        jump = np.array([le[i:i + 2].mean() / (le[max(0, i - 2):i].mean() + 1e-6) for i in range(2, len(le) - 1)])
        for i in np.argsort(-jump)[:3]:
            if jump[i] > 1.4: drops.append(round(float(downs[i + 2]), 3))
    # changements de section (nouveauté du timbre/harmonie)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    mf = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
    feat = librosa.util.sync(np.vstack([chroma, mf / 50]), beats, aggregate=np.median)
    try:
        k = max(2, min(10, int(len(bt) / 32)))
        b_idx = librosa.segment.agglomerative(feat, k)
        sections = [round(float(bt[min(i, len(bt) - 1)]), 3) for i in b_idx]
    except Exception:
        sections = []
    return dict(fichier=path, duree=round(len(y) / sr, 3), bpm=round(tempo, 2), temps=[round(float(x), 3) for x in bt],
                mesures=[round(float(x), 3) for x in downs], energie_par_mesure=[round(x, 4) for x in e_bar],
                drops=sorted(drops), sections=sections)

if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = analyser(p); out = p.rsplit('.', 1)[0] + '.rythme.json'
        json.dump(r, open(out, 'w'), indent=1)
        print(f"{p}: {r['duree']:.1f}s · {r['bpm']} BPM · {len(r['mesures'])} mesures · drops {r['drops']} · sections {r['sections']}")
