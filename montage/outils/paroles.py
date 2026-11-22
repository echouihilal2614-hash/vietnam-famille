"""Transcription des paroles des rushes (français, anglais, arabe, vietnamien… détection automatique),
avec le minutage de chaque mot : sert à repérer les phrases cultes et à faire les sous-titres façon TikTok.

Usage : python3 paroles.py <dossier_ou_fichiers...> --sortie <dossier> [--modele small|medium]
Produit <sortie>/paroles.json (mots minutés par fichier) et <sortie>/paroles.md (lecture rapide)."""
import os, sys, json, argparse, subprocess
import numpy as np
os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
from faster_whisper import WhisperModel

VID = ('.mov', '.mp4', '.m4v', '.avi', '.mkv', '.3gp', '.mts', '.webm', '.mp3', '.m4a', '.wav')

def a_du_son(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', p],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())

def transcrire(model, p):
    # audio décodé par ffmpeg (16 kHz mono) puis passé en tableau : évite le décodeur interne
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'], capture_output=True, check=True)
    audio = np.frombuffer(r.stdout, np.float32)
    if True:
        segs, info = model.transcribe(audio, word_timestamps=True, vad_filter=True, multilingual=True,
                                      vad_parameters=dict(min_silence_duration_ms=400), beam_size=5)
        out = []
        for s in segs:
            out.append(dict(debut=round(s.start, 2), fin=round(s.end, 2), texte=s.text.strip(),
                            mots=[dict(mot=w.word.strip(), debut=round(w.start, 2), fin=round(w.end, 2), conf=round(w.probability, 2))
                                  for w in (s.words or [])]))
        return dict(langue=info.language, proba_langue=round(info.language_probability, 2), segments=out)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('entrees', nargs='+'); ap.add_argument('--sortie', required=True)
    ap.add_argument('--modele', default='small'); a = ap.parse_args()
    fichiers = []
    for e in a.entrees:
        if os.path.isdir(e):
            for root, _, fs in os.walk(e):
                fichiers += [os.path.join(root, f) for f in sorted(fs) if f.lower().endswith(VID)]
        else: fichiers.append(e)
    os.makedirs(a.sortie, exist_ok=True)
    jpath = os.path.join(a.sortie, 'paroles.json')
    res = json.load(open(jpath)) if os.path.exists(jpath) else {}
    model = WhisperModel(a.modele, device='cpu', compute_type='int8', cpu_threads=os.cpu_count())
    for p in fichiers:
        cle = os.path.basename(p)
        if cle in res or not a_du_son(p): continue
        res[cle] = transcrire(model, p)
        json.dump(res, open(jpath, 'w'), indent=1, ensure_ascii=False)
        n = sum(len(s['segments']) for s in [res[cle]])
        print(f'{cle}: {res[cle]["langue"]} · {n} phrases')
    with open(os.path.join(a.sortie, 'paroles.md'), 'w') as f:
        for cle, r in sorted(res.items()):
            if not r['segments']: continue
            f.write(f'## {cle} ({r["langue"]})\n')
            for s in r['segments']: f.write(f'- `{s["debut"]:6.2f}–{s["fin"]:6.2f}` {s["texte"]}\n')
            f.write('\n')
