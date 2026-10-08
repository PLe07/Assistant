# Ce qu'il te reste à faire

Seulement ce que le tableau de bord ne peut pas faire à ta place.

## 1. Installer sur le Mac (5 minutes, indispensable)

Dans le Terminal :

```
cd ~/Assistant
git pull origin claude/auto-email-sorting-module-g4cfa4
cd tableau-de-bord
./install.sh
```

À la fin, tu dois lire `✅ Le tableau de bord est installé.` L'installation vérifie toute seule que le démon
tourne, qu'il est relancé après un arrêt brutal, que la page répond, et que les autres projets n'ont pas bougé.

- macOS peut demander d'**autoriser les notifications** (« Script Editor » ou « python3 ») : réponds **Autoriser**.
- Le Nettoyeur de démarrage te signalera une fois le nouvel élément `com.<ta session>.tableau` : c'est normal, garde-le.
- Une icône 🟢 apparaît dans la barre des menus.

Ensuite, **copie-moi ce qu'affiche** :

```
tableau etat
```

(c'est le premier état réel de tes modules, pour le rapport final).

## 2. Le coût réel de Claude (facultatif)

Sans rien faire, les crédits sont **estimés** à partir de ce que chaque module note. Pour comparer avec le **coût
réel** facturé à ton organisation Anthropic, il faut une clé **Admin** (`sk-ant-admin…`, créée dans la console
Anthropic → Settings → Admin keys). C'est la seule connexion vers Internet du tableau de bord, une fois par heure au
plus.

```
security add-generic-password -a "$USER" -s tableau-de-bord-admin-anthropic -w
```

(colle la clé quand c'est demandé), puis ajoute ces deux lignes à
`~/Library/Application Support/TableauDeBord/reglages.toml` :

```
[credits]
api_admin = true
```

## 3. La grande vérification sur le Mac (facultatif, 40 minutes)

Le faux écosystème complet et la mesure de performance de 30 minutes, avec de vrais LaunchAgents de test
`com.<ta session>.tdbtest.*` (tous retirés à la fin, même en cas d'échec) :

```
cd ~/Assistant/tableau-de-bord
TDB_VRAI_LAUNCHD=1 ./check.sh --complet
```

Tu dois lire `CHECK OK` à la fin. Aucune notification ne s'affiche pendant ce test.
