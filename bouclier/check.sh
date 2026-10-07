#!/usr/bin/env bash
# La porte unique de Bouclier : tout doit être vert avant chaque commit.
# Usage (depuis n'importe où) :  ./check.sh        (PYTHON=… pour choisir l'interpréteur)
set -u
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
echoues=()

etape() {
  local nom=$1; shift
  echo "▶ $nom"
  if "$@"; then echo "  ✅ $nom"; else echo "  ❌ $nom"; echoues+=("$nom"); fi
}

tests() {  # un groupe de tests, la couverture s'additionne d'un groupe à l'autre
  "$PY" -m pytest -q "$@" --cov=bouclier --cov-append --cov-report= --cov-fail-under=0
}

rm -f .coverage
etape "intégrité des autres projets (début)" ./integrite/verifier.sh
etape "ruff check" "$PY" -m ruff check bouclier tests integrite outils
etape "ruff format" "$PY" -m ruff format --check bouclier tests integrite outils
etape "mypy" "$PY" -m mypy bouclier
etape "pytest : unitaires et intégrité" tests tests/unitaires tests/integrite
etape "corpus d'arnaques (principal + 2e corpus inédit)" tests tests/corpus_arnaques
etape "inventaire des comptes et fuites" tests tests/comptes tests/fuites
etape "métadonnées et fiche urgence" tests tests/metadonnees tests/urgence
etape "sécurité, réseau, vie privée" tests tests/securite
etape "bout en bout (démon, doctor, installation)" tests tests/e2e
etape "couverture ≥ 90 % sur bouclier/" "$PY" -m coverage report --fail-under=90
etape "intégrité des autres projets (fin)" ./integrite/verifier.sh

echo
if [ ${#echoues[@]} -eq 0 ]; then
  echo "CHECK OK"
else
  echo "CHECK ÉCHOUÉ :"
  for e in "${echoues[@]}"; do echo "  - $e"; done
  exit 1
fi
