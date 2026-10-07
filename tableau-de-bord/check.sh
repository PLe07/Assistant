#!/usr/bin/env bash
# La porte unique du tableau de bord (§9.6) : tout doit être vert avant chaque commit.
# Usage :  ./check.sh             (rapide : intégrité, ruff, mypy, tests, couverture ≥ 90 %, intégrité)
#          ./check.sh --complet   (en plus : le faux écosystème complet et la mesure de performance, longs)
set -u
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
COMPLET=0
[ "${1:-}" = "--complet" ] && COMPLET=1
echoues=()

etape() {
  local nom=$1; shift
  echo "▶ $nom"
  if "$@"; then echo "  ✅ $nom"; else echo "  ❌ $nom"; echoues+=("$nom"); fi
}

tests() {  # un groupe de tests ; la couverture s'additionne d'un groupe à l'autre
  "$PY" -m pytest -q "$@" --cov=tableau --cov-append --cov-report= --cov-fail-under=0
}

groupe() {  # un groupe qui n'existe pas encore (phase à venir) n'est pas une erreur
  ls "$1"/test_*.py >/dev/null 2>&1 || { echo "  (pas encore de tests ici)"; return 0; }
  tests "$1"
}

groupe_long() {  # les tests marqués « complet » d'un dossier (le marqueur est exclu par défaut)
  ls "$1"/test_*.py >/dev/null 2>&1 || { echo "  (pas encore de tests ici)"; return 0; }
  tests -m complet "$1"
}

rm -f .coverage .coverage.*
etape "intégrité des autres projets (début)" ./integrite/verifier.sh
etape "ruff check" "$PY" -m ruff check tableau tests integrite outils
etape "ruff format" "$PY" -m ruff format --check tableau tests integrite outils
etape "mypy" "$PY" -m mypy tableau
etape "socle, sondes, analyses, alertes (unitaires)" groupe tests/unitaires
etape "lecture seule (copies SQLite, journaux, commandes, lsof)" groupe tests/lecture_seule
etape "adaptateurs sur les échantillons réels et déduits" groupe tests/adaptateurs
etape "gardien d'intégrité" groupe tests/integrite
etape "page web : sécurité" groupe tests/securite
etape "page web : rendu, direct, accessibilité" groupe tests/web
etape "bout en bout (démon, CLI, installation)" groupe tests/e2e
if [ $COMPLET -eq 1 ]; then
  etape "faux écosystème complet (§9.1)" groupe_long tests/faux_ecosysteme
  etape "performance (§9.5)" groupe_long tests/perf
fi
etape "couverture ≥ 90 % sur tableau/" "$PY" -m coverage report --fail-under=90
etape "intégrité des autres projets (fin)" ./integrite/verifier.sh

echo
if [ ${#echoues[@]} -eq 0 ]; then
  echo "CHECK OK"
else
  echo "CHECK ÉCHOUÉ :"
  for e in "${echoues[@]}"; do echo "  - $e"; done
  exit 1
fi
