#!/usr/bin/env bash
# La porte unique de Voix (§9.5) : tout doit être vert avant chaque commit.
# Usage :  ./check.sh             (intégrité, Swift, ruff, mypy, tests et couverture ≥ 90 %, corpus de phrases,
#                                  sécurité, intégrité)
#          ./check.sh --complet   (en plus : corpus audio, banc d'essai, mot d'éveil — longs)
set -u
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
COMPLET=0
[ "${1:-}" = "--complet" ] && COMPLET=1
echoues=()

# Swift : celui du Mac (Command Line Tools), sinon celui du conteneur de construction.
SWIFT="$(command -v swift || true)"
[ -z "$SWIFT" ] && [ -x /opt/swift-6.2.4/usr/bin/swift ] && SWIFT=/opt/swift-6.2.4/usr/bin/swift

etape() {
  local nom=$1; shift
  echo "▶ $nom"
  if "$@"; then echo "  ✅ $nom"; else echo "  ❌ $nom"; echoues+=("$nom"); fi
}

tests() {  # un groupe de tests ; la couverture s'additionne d'un groupe à l'autre
  "$PY" -m pytest -q "$@" --cov=voix --cov-append --cov-report= --cov-fail-under=0
}

groupe() {  # un groupe qui n'existe pas encore (phase à venir) n'est pas une erreur
  ls "$1"/test_*.py >/dev/null 2>&1 || { echo "  (pas encore de tests ici)"; return 0; }
  tests "$1"
}

groupe_long() {  # les tests marqués « complet » d'un dossier (exclus par défaut)
  ls "$1"/test_*.py >/dev/null 2>&1 || { echo "  (pas encore de tests ici)"; return 0; }
  tests -m complet "$1"
}

swift_build() {
  [ -n "$SWIFT" ] || { echo "  swift introuvable (sur le Mac : xcode-select --install)"; return 1; }
  (cd app && "$SWIFT" build -c release 2>&1 | tail -3; exit "${PIPESTATUS[0]}")
}

swift_controles() {  # les vérifications du Core, sans XCTest (même code que les tests XCTest)
  (cd app && "$SWIFT" run -c release controles-core 2>&1 | tail -5; exit "${PIPESTATUS[0]}")
}

swift_xctest() {
  local sortie code
  sortie="$(cd app && "$SWIFT" test 2>&1)"; code=$?
  if [ $code -ne 0 ] && printf '%s' "$sortie" | grep -q "no such module 'XCTest'"; then
    # Les seuls Command Line Tools n'ont pas XCTest : les mêmes contrôles viennent de passer par controles-core.
    echo "  XCTest absent sur ce Mac (Command Line Tools seuls) : contrôles identiques passés par controles-core"
    return 0
  fi
  printf '%s\n' "$sortie" | grep -E "error:|failed" | grep -v "0 failures" | head -10
  printf '%s\n' "$sortie" | grep -E "Executed [0-9]+ tests?" | tail -1
  return $code
}

rm -f .coverage .coverage.*
etape "intégrité des autres projets (début)" ./integrite/verifier.sh
etape "swift build -c release" swift_build
etape "swift : contrôles du Core (sans XCTest)" swift_controles
etape "swift test (XCTest)" swift_xctest
etape "ruff check" "$PY" -m ruff check voix tests integrite outils
etape "ruff format" "$PY" -m ruff format --check voix tests integrite outils
etape "mypy" "$PY" -m mypy voix
etape "socle (unitaires)" groupe tests/unitaires
etape "compréhension : grammaire et corpus de phrases (§9.1)" groupe tests/nlu
etape "actions, annulation, confirmation (§9.3)" groupe tests/actions
etape "sécurité : injection, recherche automatisée (§9.3)" groupe tests/securite
etape "corpus audio : fabrication, banc d'essai rapide (§9.2)" groupe tests/corpus_audio
etape "intégration : moteur, socket, démon" groupe tests/integration
etape "gardien d'intégrité" groupe tests/integrite
if [ $COMPLET -eq 1 ]; then
  etape "corpus audio et banc d'essai (§9.2)" groupe_long tests/corpus_audio
  etape "ressources et latence (§5.3)" groupe_long tests/perf
fi
etape "couverture ≥ 90 % sur voix/" "$PY" -m coverage report --fail-under=90
etape "intégrité des autres projets (fin)" ./integrite/verifier.sh

echo
if [ ${#echoues[@]} -eq 0 ]; then
  echo "CHECK OK"
else
  echo "CHECK ÉCHOUÉ :"
  for e in "${echoues[@]}"; do echo "  - $e"; done
  exit 1
fi
