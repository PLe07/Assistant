#!/usr/bin/env bash
# Retire Bouclier de ton Mac (relançable). Tes données (historique, inventaire, fiche urgence) restent, sauf avec
# --tout. Le dossier iCloud Drive/Bouclier et ce dossier du projet restent toujours : à toi de les supprimer.
# Usage : ./uninstall.sh   ou   ./uninstall.sh --tout
set -u
ICI="$(cd "$(dirname "$0")" && pwd)"
cd "$ICI" || exit 1

arreter() { printf '\n❌ %s\n' "$*"; exit 1; }

[ "$(id -u)" != "0" ] || arreter "Ne lance pas uninstall.sh avec sudo."
[ "$(uname -s)" = "Darwin" ] || arreter "Bouclier s'installe et se retire sur un Mac (macOS)."
TOUT=""
case "${1:-}" in
  "") ;;
  --tout) TOUT="--tout" ;;
  *) arreter "option inconnue : ${1} (seule --tout existe)" ;;
esac

MAISON="${BOUCLIER_MAISON:-$HOME}"
PY="$ICI/.venv/bin/python"
[ -x "$PY" ] || arreter "$ICI/.venv absent : relance d'abord ./install.sh, puis ./uninstall.sh"
B() { "$PY" -m bouclier "$@"; }

INTEGRITE_MAC="${BOUCLIER_INTEGRITE_MAC:-$ICI/integrite/mac}"
mkdir -p "$INTEGRITE_MAC" && chmod 700 "$INTEGRITE_MAC"
AVANT="$INTEGRITE_MAC/avant_desinstallation.json"
"$PY" integrite/empreinte.py capturer "$AVANT" || arreter "empreinte impossible : rien n'est retiré"
chmod 600 "$AVANT"

LABEL="$(B installation label)"
DOMAINE="gui/$(id -u)"
if launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAINE/$LABEL" >/dev/null 2>&1
  for _ in $(seq 1 40); do launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1 || break; sleep 0.5; done
  launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1 && arreter "launchd n'arrête pas $LABEL : rien d'autre n'est retiré"
  echo "  ✅ surveillance arrêtée : $LABEL"
fi
B installation desinstaller $TOUT

echo
"$PY" integrite/empreinte.py comparer "$AVANT" || arreter "les autres projets ont changé pendant la désinstallation (voir ci-dessus)"
echo
echo "✅ Bouclier est retiré. Restent : le dossier iCloud Drive/Bouclier et ce dossier ($ICI)."
[ -n "$TOUT" ] || echo "Tes données restent dans $MAISON/Library/Application Support/Bouclier (./uninstall.sh --tout pour les retirer)."
