#!/bin/bash
# Prépare l'atelier de montage (Linux ou macOS) :
# environnement Python isolé (.venv), bibliothèques, effets sonores et musiques provisoires.
# Prérequis : ffmpeg (sur Mac : `brew install ffmpeg`) et python3.
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "ffmpeg manquant : sur Mac, lance d'abord « brew install ffmpeg »"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
PY=.venv/bin/python
$PY -m pip install -q --upgrade pip
$PY -m pip install -q numpy scipy soundfile librosa opencv-python-headless pillow pillow-heif fonttools brotli faster-whisper
# polices : le moteur les charge directement depuis fonts/ (rien à installer dans le système)
if command -v fc-cache >/dev/null && [ "$(uname)" = "Linux" ]; then mkdir -p ~/.fonts && cp fonts/*.ttf ~/.fonts/ && fc-cache -f >/dev/null; fi
[ -f sons/clavier_1.wav ] || $PY outils/sons.py
[ -f musique/vacances.wav ] || $PY outils/musique.py
echo "Atelier prêt. Lancer les scripts avec : montage/.venv/bin/python <script>"
