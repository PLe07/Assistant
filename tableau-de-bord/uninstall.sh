#!/usr/bin/env bash
# Retire le tableau de bord de ton Mac (relançable). Il ne laisse rien derrière lui : son agent, sa commande, ses
# données, ses journaux, son instantané iCloud et son environnement Python. Aucun autre module n'est touché.
# Ce dossier du projet reste (c'est le dépôt) ; ta clé Admin facultative reste dans le trousseau, sauf si tu dis oui.
# Usage : ./uninstall.sh
set -u
ICI="$(cd "$(dirname "$0")" && pwd)"
cd "$ICI" || exit 1

arreter() { printf '\n❌ %s\n' "$*"; exit 1; }

[ "$(id -u)" != "0" ] || arreter "Ne lance pas uninstall.sh avec sudo."
[ "$(uname -s)" = "Darwin" ] || arreter "Le tableau de bord se retire sur un Mac (macOS)."

PY="$ICI/.venv/bin/python"
[ -x "$PY" ] || arreter "$ICI/.venv absent : relance d'abord ./install.sh, puis ./uninstall.sh"
T() { "$PY" -m tableau "$@"; }

INTEGRITE_MAC="${TABLEAU_INTEGRITE_MAC:-$ICI/integrite/mac}"
mkdir -p "$INTEGRITE_MAC" && chmod 700 "$INTEGRITE_MAC"
AVANT="$INTEGRITE_MAC/avant_desinstallation.json"
"$PY" integrite/empreinte.py capturer "$AVANT" || arreter "empreinte impossible : rien n'est retiré"
chmod 600 "$AVANT"

LABEL="$(T installation label)"
DOMAINE="gui/$(id -u)"
if launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAINE/$LABEL" >/dev/null 2>&1
  for _ in $(seq 1 40); do launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1 || break; sleep 0.5; done
  launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1 && arreter "launchd n'arrête pas $LABEL : rien d'autre n'est retiré"
  echo "  ✅ démon arrêté : $LABEL"
fi

T installation desinstaller || arreter "désinstallation incomplète (voir ❌ ci-dessus)"

if security find-generic-password -s tableau-de-bord-admin-anthropic >/dev/null 2>&1; then
  printf "Ta clé Admin Anthropic (facultative) est dans le trousseau. La supprimer aussi ? [o/N] "
  read -r REPONSE
  case "$REPONSE" in
    o|O|oui|Oui|OUI) security delete-generic-password -s tableau-de-bord-admin-anthropic >/dev/null && echo "  ✅ clé retirée" ;;
    *) echo "  clé gardée" ;;
  esac
fi

echo
INTEGRITE=0
"$PY" integrite/empreinte.py comparer "$AVANT" || INTEGRITE=1
if [ -f "$ICI/.venv/.tableau-installe" ]; then
  rm -rf "$ICI/.venv"
  echo "  ✅ environnement Python retiré (.venv)"
fi
[ "$INTEGRITE" -eq 0 ] || arreter "les autres projets ont changé pendant la désinstallation (voir ci-dessus)"
echo
echo "✅ Le tableau de bord est retiré. Reste seulement ce dossier ($ICI)."
