#!/usr/bin/env bash
# La porte unique de Quotidien (§10.6) : tout doit être vert avant chaque commit.
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
  "$PY" -m pytest -q "$@" --cov=quotidien --cov-append --cov-report= --cov-fail-under=0
}

groupe() {  # un groupe qui n'existe pas encore (phase à venir) n'est pas une erreur
  local present=()
  for d in "$@"; do ls "$d"/test_*.py >/dev/null 2>&1 && present+=("$d"); done
  [ ${#present[@]} -eq 0 ] && { echo "  (pas encore de tests ici)"; return 0; }
  tests "${present[@]}"
}

rm -f .coverage
etape "intégrité des autres projets (début)" ./integrite/verifier.sh
etape "ruff check" "$PY" -m ruff check quotidien tests integrite outils
etape "ruff format" "$PY" -m ruff format --check quotidien tests integrite outils
etape "mypy" "$PY" -m mypy quotidien
etape "pytest : socle et intégrité" groupe tests/socle tests/integrite
etape "météo « habille-toi »" groupe tests/meteo
etape "recettes, menu et courses (dont propriétés hypothesis)" groupe tests/repas
etape "vide-frigo" groupe tests/frigo
etape "anniversaires" groupe tests/anniversaires
etape "brief, Rappels, iCloud, raccourcis" groupe tests/brief
etape "sécurité, réseau, aucune capacité d'envoi" groupe tests/securite
etape "bout en bout (démon, doctor, installation)" groupe tests/e2e
etape "couverture ≥ 90 % sur quotidien/" "$PY" -m coverage report --fail-under=90
etape "intégrité des autres projets (fin)" ./integrite/verifier.sh

echo
if [ ${#echoues[@]} -eq 0 ]; then
  echo "CHECK OK"
else
  echo "CHECK ÉCHOUÉ :"
  for e in "${echoues[@]}"; do echo "  - $e"; done
  exit 1
fi
