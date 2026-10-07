#!/usr/bin/env bash
# Vérifie que les projets existants sont exactement dans leur état « avant » (lecture seule).
# - Sur ton Mac : la référence est integrite/mac/etat_avant.json, prise par install.sh avant toute installation
#   (ou ici même, la toute première fois, si elle n'existe pas encore).
# - Ailleurs (conteneur de construction) : integrite/etat_avant.json.
set -u
ICI="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
if [ "$(uname -s)" = "Darwin" ]; then
  REF="${QUOTIDIEN_INTEGRITE_MAC:-$ICI/mac}/etat_avant.json"
  if [ ! -f "$REF" ]; then
    echo "Première vérification sur ce Mac : empreinte « avant » prise maintenant."
    mkdir -p "$(dirname "$REF")" && chmod 700 "$(dirname "$REF")"
    "$PY" "$ICI/empreinte.py" capturer "$REF" || exit 1
    chmod 600 "$REF"
  fi
else
  REF="$ICI/etat_avant.json"
fi
exec "$PY" "$ICI/empreinte.py" comparer "$REF"
