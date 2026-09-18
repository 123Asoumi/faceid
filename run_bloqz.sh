#!/usr/bin/env bash
# BLOQZ launcher (Linux/macOS)
cd "$(dirname "$0")" || exit 1
if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi
exec python3 isdhine.py
