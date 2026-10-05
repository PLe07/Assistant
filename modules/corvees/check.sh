#!/usr/bin/env bash
# La porte unique du détecteur de corvées : tout doit être vert avant chaque commit.
# Usage (depuis n'importe où) :  modules/corvees/check.sh      (PYTHON=… pour choisir l'interpréteur)
set -u
cd "$(dirname "$0")/../.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
CIBLES=(modules/corvees tests/corvees corvees.py)
echoues=()

etape() {
  local nom=$1; shift
  echo "▶ $nom"
  if "$@"; then echo "  ✅ $nom"; else echo "  ❌ $nom"; echoues+=("$nom"); fi
}

etape "ruff check" "$PY" -m ruff check "${CIBLES[@]}"
etape "ruff format" "$PY" -m ruff format --check "${CIBLES[@]}"
etape "mypy" "$PY" -m mypy modules/corvees corvees.py
etape "pytest + couverture ≥ 85 %" "$PY" -m pytest -q -p no:cacheprovider tests/corvees/unitaires tests/corvees/vie_privee \
  tests/corvees/e2e --cov --cov-report=term-missing
etape "simulation (5 graines + 2e jeu)" "$PY" -m pytest -q -p no:cacheprovider tests/corvees/simulation
etape "performance" "$PY" -m pytest -q -p no:cacheprovider tests/corvees/perf

echo
if [ ${#echoues[@]} -eq 0 ]; then
  echo "CHECK OK"
else
  echo "CHECK ÉCHOUÉ :"
  for e in "${echoues[@]}"; do echo "  - $e"; done
  exit 1
fi
