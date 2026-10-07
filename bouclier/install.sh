#!/usr/bin/env bash
# Installe Bouclier sur ton Mac, pour ta session seulement (jamais de sudo). Relançable sans effet de bord :
# une deuxième fois, il met à jour ce qui a changé et revérifie tout.
# Usage : ./install.sh
set -u
ICI="$(cd "$(dirname "$0")" && pwd)"
cd "$ICI" || exit 1

titre() { printf '\n▶ %s\n' "$*"; }
arreter() { printf '\n❌ %s\n' "$*"; exit 1; }

[ "$(id -u)" != "0" ] || arreter "Ne lance pas install.sh avec sudo : Bouclier s'installe seulement pour ta session."
[ "$(uname -s)" = "Darwin" ] || arreter "Bouclier s'installe sur un Mac (macOS)."

MAISON="${BOUCLIER_MAISON:-$HOME}"
LOGS="$MAISON/Library/Logs/Bouclier"
mkdir -p "$LOGS" && chmod 700 "$LOGS"
JOURNAL="$LOGS/installation-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$JOURNAL") 2>&1

# --- 1. Python 3.11 ou plus (D-07) -------------------------------------------------------------------------------
titre "1/8 Python 3.11 ou plus"
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

# --- 2. Empreinte des autres projets, avant ----------------------------------------------------------------------
titre "2/8 Empreinte des autres projets (avant)"
INTEGRITE_MAC="${BOUCLIER_INTEGRITE_MAC:-$ICI/integrite/mac}"
mkdir -p "$INTEGRITE_MAC" && chmod 700 "$INTEGRITE_MAC"
PYTHON="$PY" ./integrite/verifier.sh || echo "  ⚠️ différent de la toute première empreinte (voir ci-dessus) : ce n'est pas cette installation"
AVANT="$INTEGRITE_MAC/avant_installation.json"
"$PY" integrite/empreinte.py capturer "$AVANT" || arreter "empreinte impossible : rien n'est installé"
chmod 600 "$AVANT"

# --- 3. Environnement Python de Bouclier (dans ce dossier) -------------------------------------------------------
titre "3/8 Environnement Python de Bouclier"
VENV="$ICI/.venv"
if [ -x "$VENV/bin/python" ] && ! python_ok "$VENV/bin/python"; then
  echo "  .venv trop ancien : recréé"
  rm -rf "$VENV"
fi
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV" || arreter "création de .venv impossible"
B() { "$VENV/bin/python" -m bouclier "$@"; }
EMPREINTE="$("$PY" -c 'import hashlib; print(hashlib.sha256(open("pyproject.toml", "rb").read()).hexdigest())')"
if [ "$(cat "$VENV/.bouclier-installe" 2>/dev/null)" = "$EMPREINTE" ] && "$VENV/bin/python" -c 'import bouclier.cli' 2>/dev/null; then
  echo "  déjà à jour"
else
  "$VENV/bin/python" -m pip install --quiet --upgrade pip || arreter "pip ne se met pas à jour (réseau ?)"
  "$VENV/bin/python" -m pip install --quiet -e ".[dev]" || arreter "installation des paquets impossible (réseau ?)"
  echo "$EMPREINTE" > "$VENV/.bouclier-installe"
  echo "  paquets installés"
fi

# --- 4. Ce que Bouclier pose : dossiers, réglages, commande, actions rapides, agent ---------------------------------
titre "4/8 Dossiers, commande bouclier, actions rapides, agent de démarrage"
B installation preparer --python "$VENV/bin/python" --projet "$ICI" || arreter "installation arrêtée (voir ❌ ci-dessus) : rien d'autre n'a été touché"

# --- 5. Raccourcis iPhone -------------------------------------------------------------------------------------------
titre "5/8 Raccourcis « Arnaque ? » et « Envoyer sans traces »"
B installation raccourcis

# --- 6. Démarrage du démon (launchd) -------------------------------------------------------------------------------
titre "6/8 Démarrage de la surveillance"
LABEL="$(B installation label)"
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

# --- 7. Vérification réelle : kill puis relance, aller-retour iCloud ------------------------------------------------
titre "7/8 Vérification : arrêt brutal puis relance, demande déposée dans iCloud"
VERIF=0
B installation verifier || VERIF=1

# --- 8. Bilan ----------------------------------------------------------------------------------------------------------
titre "8/8 Bilan"
B doctor
echo
INTEGRITE=0
"$PY" integrite/empreinte.py comparer "$AVANT" || INTEGRITE=1
echo
if [ "$VERIF" -ne 0 ] || [ "$INTEGRITE" -ne 0 ]; then
  echo "⚠️ Installé, mais une vérification a échoué (voir ci-dessus). Journal : $JOURNAL"
  exit 1
fi
echo "✅ Bouclier est installé et surveille. Journal de l'installation : $JOURNAL"
echo "Il te reste : ACTIONS_HUMAINES.md (raccourcis à ajouter sur l'iPhone, Gmail à relier)."
