#!/usr/bin/env bash
# =====================================================================
# BLOQZ / Isdhine — compilation d'un executable Linux (PyInstaller)
# ---------------------------------------------------------------------
# Produit un binaire autonome (equivalent d'un .exe) dans dist/BLOQZ.
# A lancer sur la machine/distribution cible : un binaire PyInstaller
# n'est pas garanti portable entre distributions (glibc differente).
#
# Usage :
#   ./build-linux.sh
# Resultat :
#   dist/BLOQZ   <- l'executable a distribuer / lancer
# =====================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

# 1. Environnement virtuel
if [ ! -d ".venv" ]; then
    echo ">> Creation de l'environnement virtuel (.venv)"
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2. Dependances (app + PyInstaller)
echo ">> Installation des dependances"
pip install --upgrade pip
pip install -r requirements.txt
pip install "pyinstaller>=6.0"

# 3. Nettoyage des builds precedents
echo ">> Nettoyage"
rm -rf build dist

# 4. Compilation via le fichier .spec fourni
echo ">> Compilation (PyInstaller)"
pyinstaller --clean --noconfirm BLOQZ.spec

# 5. Resultat
if [ -f "dist/BLOQZ" ]; then
    chmod +x dist/BLOQZ
    echo ""
    echo "==================================================="
    echo " OK : executable cree -> $APP_DIR/dist/BLOQZ"
    echo " Lancement :  ./dist/BLOQZ"
    echo "==================================================="
else
    echo "!! La compilation semble avoir echoue : dist/BLOQZ introuvable." >&2
    exit 1
fi
