#!/usr/bin/env bash
# Retire Quotidien de ton Mac (relançable). Te demande si tu veux supprimer tes listes de Rappels créées par
# Quotidien (et seulement elles). Tes données (menus, notes, frigo) restent, sauf avec --tout.
# Le dossier iCloud Drive/Quotidien et ce dossier du projet restent toujours : à toi de les supprimer.
# Usage : ./uninstall.sh   ou   ./uninstall.sh --tout
set -u
ICI="$(cd "$(dirname "$0")" && pwd)"
cd "$ICI" || exit 1

arreter() { printf '\n❌ %s\n' "$*"; exit 1; }

[ "$(id -u)" != "0" ] || arreter "Ne lance pas uninstall.sh avec sudo."
[ "$(uname -s)" = "Darwin" ] || arreter "Quotidien s'installe et se retire sur un Mac (macOS)."
TOUT=""
case "${1:-}" in
  "") ;;
  --tout) TOUT="--tout" ;;
  *) arreter "option inconnue : ${1} (seule --tout existe)" ;;
esac

PY="$ICI/.venv/bin/python"
[ -x "$PY" ] || arreter "$ICI/.venv absent : relance d'abord ./install.sh, puis ./uninstall.sh"
Q() { "$PY" -m quotidien "$@"; }

INTEGRITE_MAC="${QUOTIDIEN_INTEGRITE_MAC:-$ICI/integrite/mac}"
mkdir -p "$INTEGRITE_MAC" && chmod 700 "$INTEGRITE_MAC"
AVANT="$INTEGRITE_MAC/avant_desinstallation.json"
"$PY" integrite/empreinte.py capturer "$AVANT" || arreter "empreinte impossible : rien n'est retiré"
chmod 600 "$AVANT"

LABEL="$(Q installation label)"
DOMAINE="gui/$(id -u)"
if launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAINE/$LABEL" >/dev/null 2>&1
  for _ in $(seq 1 40); do launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1 || break; sleep 0.5; done
  launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1 && arreter "launchd n'arrête pas $LABEL : rien d'autre n'est retiré"
  echo "  ✅ démon arrêté : $LABEL"
fi

LISTES="$(Q installation listes)"
if [ "$LISTES" != "(aucune liste créée par Quotidien)" ]; then
  echo
  echo "Listes de Rappels créées par Quotidien :"
  echo "$LISTES" | sed 's/^/  • /'
  printf "Les supprimer (et leurs rappels) ? Les autres listes ne sont jamais touchées. [o/N] "
  read -r REPONSE
  case "$REPONSE" in
    o|O|oui|Oui|OUI) Q installation supprimer-listes ;;
    *) echo "  listes gardées" ;;
  esac
fi

Q installation desinstaller $TOUT

echo
"$PY" integrite/empreinte.py comparer "$AVANT" || arreter "les autres projets ont changé pendant la désinstallation (voir ci-dessus)"
echo
echo "✅ Quotidien est retiré. Restent : le dossier iCloud Drive/Quotidien et ce dossier ($ICI)."
[ -n "$TOUT" ] || echo "Tes données restent dans ~/Library/Application Support/Quotidien (./uninstall.sh --tout pour les retirer)."
