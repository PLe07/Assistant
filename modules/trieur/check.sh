#!/usr/bin/env bash
# La porte unique du Trieur : tout doit être vert avant chaque commit.
# Usage (depuis n'importe où) :  modules/trieur/check.sh      (PYTHON=… pour choisir l'interpréteur)
set -u
cd "$(dirname "$0")/../.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
CIBLES=(modules/trieur tests/trieur trieur.py)
echoues=()

etape() {
  local nom=$1; shift
  echo "▶ $nom"
  if "$@"; then echo "  ✅ $nom"; else echo "  ❌ $nom"; echoues+=("$nom"); fi
}

etape "ruff check" "$PY" -m ruff check "${CIBLES[@]}"
etape "ruff format" "$PY" -m ruff format --check "${CIBLES[@]}"
etape "mypy" "$PY" -m mypy modules/trieur trieur.py
etape "pytest + couverture ≥ 85 %" "$PY" -m pytest -q -p no:cacheprovider tests/trieur/unitaires tests/trieur/ia \
  tests/trieur/e2e --cov=modules/trieur --cov-config=modules/trieur/.coveragerc --cov-report=term-missing
etape "corpus (principal + 2e corpus inédit)" "$PY" -m pytest -q -p no:cacheprovider tests/trieur/corpus
etape "sécurité et vie privée" "$PY" -m pytest -q -p no:cacheprovider tests/trieur/securite
etape "performance" "$PY" -m pytest -q -p no:cacheprovider tests/trieur/perf

echo
if [ ${#echoues[@]} -eq 0 ]; then
  echo "CHECK OK"
else
  echo "CHECK ÉCHOUÉ :"
  for e in "${echoues[@]}"; do echo "  - $e"; done
  exit 1
fi
