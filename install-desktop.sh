#!/usr/bin/env bash
# =====================================================================
# BLOQZ / Isdhine — Installation du raccourci de bureau (Linux)
# ---------------------------------------------------------------------
# Ce script crée une entrée d'application (.desktop) pour que BLOQZ
# apparaisse dans le menu des applications et puisse être placé sur le
# bureau, avec son icône. Il génère automatiquement les bons chemins.
#
# Usage :
#   ./install-desktop.sh            # installe le raccourci
#   ./install-desktop.sh --uninstall  # supprime le raccourci
# =====================================================================
set -euo pipefail

# Dossier réel du projet (là où se trouve ce script)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$APP_DIR/run_bloqz.sh"
ICON="$APP_DIR/Asset/logo/icone.png"

DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/bloqz.desktop"

# --- Désinstallation -------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$DESKTOP_FILE"
    rm -f "$HOME/Desktop/bloqz.desktop" 2>/dev/null || true
    echo "Raccourci BLOQZ supprimé."
    exit 0
fi

# --- Vérifications ---------------------------------------------------
if [ ! -f "$LAUNCHER" ]; then
    echo "Erreur : run_bloqz.sh introuvable dans $APP_DIR" >&2
    exit 1
fi
chmod +x "$LAUNCHER"

if [ ! -f "$ICON" ]; then
    echo "Attention : icône introuvable ($ICON), le raccourci sera sans icône." >&2
    ICON=""
fi

mkdir -p "$DESKTOP_DIR"

# --- Génération du fichier .desktop ---------------------------------
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=BLOQZ
GenericName=Verrouillage par webcam
Comment=Verrouille l'ordinateur en cas d'absence detectee par la webcam
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Utility;Security;
Keywords=lock;webcam;security;face;absence;isdhine;bloqz;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# Rafraîchir la base des applications (si l'outil est présent)
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Raccourci installe : $DESKTOP_FILE"
echo "BLOQZ devrait maintenant apparaitre dans votre menu d'applications."

# --- Copie optionnelle sur le bureau --------------------------------
DESKTOP_HOME="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
if [ -d "$DESKTOP_HOME" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_HOME/bloqz.desktop"
    chmod +x "$DESKTOP_HOME/bloqz.desktop"
    # GNOME exige parfois de marquer le lanceur comme "de confiance"
    if command -v gio >/dev/null 2>&1; then
        gio set "$DESKTOP_HOME/bloqz.desktop" metadata::trusted true 2>/dev/null || true
    fi
    echo "Icone egalement copiee sur le bureau : $DESKTOP_HOME/bloqz.desktop"
fi
