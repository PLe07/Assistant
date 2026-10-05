#!/usr/bin/env bash
# La porte unique du Nettoyeur de démarrage : tout doit être vert avant chaque commit.
# Usage (depuis n'importe où) :  modules/demarrage/check.sh      (PYTHON=… pour choisir l'interpréteur)
set -u
cd "$(dirname "$0")/../.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
CIBLES=(modules/demarrage tests/demarrage demarrage.py)
echoues=()

etape() {
  local nom=$1; shift
  echo "▶ $nom"
  if "$@"; then echo "  ✅ $nom"; else echo "  ❌ $nom"; echoues+=("$nom"); fi
}

etape "ruff check" "$PY" -m ruff check "${CIBLES[@]}"
etape "ruff format" "$PY" -m ruff format --check "${CIBLES[@]}"
etape "mypy" "$PY" -m mypy modules/demarrage demarrage.py
etape "pytest + couverture ≥ 85 %" "$PY" -m pytest -q -p no:cacheprovider tests/demarrage/unitaires tests/demarrage/e2e \
  tests/demarrage/faux_mac \
  --cov=modules/demarrage --cov-config=modules/demarrage/.coveragerc --cov-report=term-missing
etape "faux Mac (+ 2e faux Mac, 5 graines)" "$PY" -m pytest -q -p no:cacheprovider tests/demarrage/faux_mac
etape "sécurité" "$PY" -m pytest -q -p no:cacheprovider tests/demarrage/securite
etape "performance" "$PY" -m pytest -q -p no:cacheprovider tests/demarrage/perf

echo
if [ ${#echoues[@]} -eq 0 ]; then
  echo "CHECK OK"
else
  echo "CHECK ÉCHOUÉ :"
  for e in "${echoues[@]}"; do echo "  - $e"; done
  exit 1
fi
