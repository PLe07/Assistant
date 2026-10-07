#!/usr/bin/env bash
# Installe Quotidien sur ton Mac, pour ta session seulement (jamais de sudo). Relançable sans effet de bord :
# une deuxième fois, il met à jour ce qui a changé et revérifie tout.
# Usage : ./install.sh
set -u
ICI="$(cd "$(dirname "$0")" && pwd)"
cd "$ICI" || exit 1

titre() { printf '\n▶ %s\n' "$*"; }
arreter() { printf '\n❌ %s\n' "$*"; exit 1; }

[ "$(id -u)" != "0" ] || arreter "Ne lance pas install.sh avec sudo : Quotidien s'installe seulement pour ta session."
[ "$(uname -s)" = "Darwin" ] || arreter "Quotidien s'installe sur un Mac (macOS)."

MAISON="${QUOTIDIEN_MAISON:-$HOME}"
LOGS="$MAISON/Library/Logs/Quotidien"
mkdir -p "$LOGS" && chmod 700 "$LOGS"
JOURNAL="$LOGS/installation-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$JOURNAL") 2>&1

titre "1/9 Python 3.11 ou plus"
python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }
PY=""
for candidat in "${PYTHON:-}" python3.14 python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 \
  /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3; do
  [ -n "$candidat" ] || continue
  chemin="$(command -v "$candidat" 2>/dev/null)" || continue
  if python_ok "$chemin"; then PY="$chemin"; break; fi
done
[ -n "$PY" ] || arreter "Python 3.11 ou plus introuvable : installe-le depuis python.org, puis relance ./install.sh"
echo "  $PY ($("$PY" -c 'import platform; print(platform.python_version())'))"

titre "2/9 Empreinte des autres projets (avant)"
INTEGRITE_MAC="${QUOTIDIEN_INTEGRITE_MAC:-$ICI/integrite/mac}"
mkdir -p "$INTEGRITE_MAC" && chmod 700 "$INTEGRITE_MAC"
PYTHON="$PY" ./integrite/verifier.sh || echo "  ⚠️ différent de la toute première empreinte (voir ci-dessus) : ce n'est pas cette installation"
AVANT="$INTEGRITE_MAC/avant_installation.json"
"$PY" integrite/empreinte.py capturer "$AVANT" || arreter "empreinte impossible : rien n'est installé"
chmod 600 "$AVANT"

titre "3/9 Environnement Python de Quotidien (dans ce dossier)"
VENV="$ICI/.venv"
if [ -x "$VENV/bin/python" ] && ! python_ok "$VENV/bin/python"; then
  echo "  .venv trop ancien : recréé"
  rm -rf "$VENV"
fi
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV" || arreter "création de .venv impossible"
Q() { "$VENV/bin/python" -m quotidien "$@"; }
EMPREINTE="$("$PY" -c 'import hashlib; print(hashlib.sha256(open("pyproject.toml", "rb").read()).hexdigest())')"
if [ "$(cat "$VENV/.quotidien-installe" 2>/dev/null)" = "$EMPREINTE" ] && "$VENV/bin/python" -c 'import quotidien.cli' 2>/dev/null; then
  echo "  déjà à jour"
else
  "$VENV/bin/python" -m pip install --quiet --upgrade pip || arreter "pip ne se met pas à jour (réseau ?)"
  "$VENV/bin/python" -m pip install --quiet -e ".[dev]" || arreter "installation des paquets impossible (réseau ?)"
  echo "$EMPREINTE" > "$VENV/.quotidien-installe"
  echo "  paquets installés"
fi

titre "4/9 Dossiers, profil, commande quotidien, agent de démarrage"
Q installation preparer --python "$VENV/bin/python" --projet "$ICI" || arreter "installation arrêtée (voir ❌ ci-dessus) : rien d'autre n'a été touché"

titre "5/9 Raccourcis « Mon frigo » et « Envie de… »"
Q installation raccourcis

titre "6/9 Contacts (une fenêtre de macOS peut s'ouvrir : réponds « Autoriser »)"
Q anniversaires || echo "  ⚠️ anniversaires : mode dégradé (proches.toml), voir quotidien doctor"

titre "7/9 Premier menu et premier brief, réels"
Q menu || echo "  ⚠️ menu non généré (voir ci-dessus)"
Q brief || echo "  ⚠️ brief non généré (voir ci-dessus)"

titre "8/9 Démarrage du démon (launchd), puis arrêt brutal et relance, aller-retour iCloud"
LABEL="$(Q installation label)"
DOMAINE="gui/$(id -u)"
PLIST="$MAISON/Library/LaunchAgents/$LABEL.plist"
if launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAINE/$LABEL" >/dev/null 2>&1
  for _ in $(seq 1 40); do launchctl print "$DOMAINE/$LABEL" >/dev/null 2>&1 || break; sleep 0.5; done
  echo "  ancienne version arrêtée"
fi
launchctl enable "$DOMAINE/$LABEL" >/dev/null 2>&1
launchctl bootstrap "$DOMAINE" "$PLIST" || arreter "launchd refuse de charger $PLIST (journal : $LOGS/demon.erreurs.log)"
EN_MARCHE=""
for _ in $(seq 1 30); do
  if launchctl print "$DOMAINE/$LABEL" 2>/dev/null | grep -q "pid = "; then EN_MARCHE=1; break; fi
  sleep 0.5
done
[ -n "$EN_MARCHE" ] || arreter "le démon ne démarre pas (journal : $LOGS/demon.erreurs.log)"
echo "  $LABEL en marche"
VERIF=0
Q installation verifier || VERIF=1

titre "9/9 Bilan"
Q doctor
echo
INTEGRITE=0
"$PY" integrite/empreinte.py comparer "$AVANT" || INTEGRITE=1
echo
if [ "$VERIF" -ne 0 ] || [ "$INTEGRITE" -ne 0 ]; then
  echo "⚠️ Installé, mais une vérification a échoué (voir ci-dessus). Journal : $JOURNAL"
  exit 1
fi
echo "✅ Quotidien est installé. Journal de l'installation : $JOURNAL"
echo "Il te reste : ACTIONS_HUMAINES.md (raccourcis à ajouter sur l'iPhone, accès à accepter une fois)."
