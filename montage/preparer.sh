#!/bin/bash
# Prépare l'atelier de montage dans une nouvelle session :
# bibliothèques Python, polices, effets sonores et musiques provisoires (régénérés, libres de droits).
set -e
cd "$(dirname "$0")"
pip install -q librosa soundfile scipy opencv-python-headless fonttools brotli pillow-heif faster-whisper
mkdir -p ~/.fonts && cp fonts/*.ttf ~/.fonts/ && fc-cache -f >/dev/null
[ -f sons/whoosh.wav ] || python3 outils/sons.py
[ -f musique/vacances.wav ] || python3 outils/musique.py
echo "Atelier prêt."
