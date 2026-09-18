#!/usr/bin/env bash
# =====================================================================
# BLOQZ / Isdhine — lanceur Linux/macOS
# ---------------------------------------------------------------------
# Robuste pour un lancement en terminal ET depuis une icone (.desktop) :
#  - resout son propre dossier meme via un lien symbolique
#  - utilise directement le Python du .venv si present
#  - journalise la sortie dans bloqz.log
#  - reessaie avec QT_QPA_PLATFORM=xcb si le demarrage Wayland echoue
# =====================================================================

# Dossier reel du script (gere les liens symboliques)
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
APP_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$APP_DIR" || exit 1

LOG="$APP_DIR/bloqz.log"

# Choix de l'interpreteur Python : venv en priorite
if [ -x "$APP_DIR/.venv/bin/python3" ]; then
    PY="$APP_DIR/.venv/bin/python3"
elif [ -x "$APP_DIR/.venv/bin/python" ]; then
    PY="$APP_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
else
    PY="python"
fi

echo "==== $(date) : lancement BLOQZ avec $PY ====" >> "$LOG"

# Premiere tentative : environnement natif (Wayland/X11 tel quel)
"$PY" isdhine.py >> "$LOG" 2>&1
STATUS=$?

# Si echec, nouvelle tentative en forcant le backend X11 (xcb)
if [ "$STATUS" -ne 0 ]; then
    echo "---- echec (code $STATUS), nouvelle tentative avec QT_QPA_PLATFORM=xcb ----" >> "$LOG"
    QT_QPA_PLATFORM=xcb "$PY" isdhine.py >> "$LOG" 2>&1
    STATUS=$?
fi

if [ "$STATUS" -ne 0 ]; then
    echo "!!! BLOQZ n'a pas pu demarrer (code $STATUS). Voir $LOG !!!" >> "$LOG"
fi

exit "$STATUS"
