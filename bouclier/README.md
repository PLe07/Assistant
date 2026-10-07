# Bouclier

Ton garde du corps numérique, sur ton Mac et ton iPhone. Cinq fonctions qui s'entraident :

| | Ce que ça fait | Comment tu t'en sers |
|---|---|---|
| 🛡️ **Détecteur d'arnaque** | Dit si un SMS, un mail ou une capture d'écran est une arnaque, et quoi faire | iPhone : capture d'écran → Partager → **Arnaque ?** · Mac : clic droit → **Est-ce une arnaque ?** · Gmail : tout seul |
| 📋 **Inventaire de tes comptes** | Retrouve les sites où tu as un compte (sans jamais lire un mot de passe) | `bouclier comptes` |
| 🚨 **Alerte fuite** | Te prévient quand un site où tu as un compte s'est fait voler ses données | Notification, `bouclier fuites` |
| 🧹 **Nettoyeur de métadonnées** | Enlève la position GPS, l'appareil, l'auteur d'une photo ou d'un document | Clic droit → **Nettoyer les métadonnées** · iPhone : **Envoyer sans traces** |
| 🆘 **Fiche urgence** | Les bons numéros et les bons réflexes, lisibles sans réseau | `bouclier urgence` → PDF dans iCloud |

Le tableau de bord `Bouclier.html` regroupe tout, avec un score « Hygiène numérique » et les 3 actions qui comptent
le plus : `bouclier tableau`.

---

## Installer

Dans le Terminal :

```
cd ~/Assistant
git pull origin claude/auto-email-sorting-module-g4cfa4
cd bouclier
./install.sh
```

`install.sh` peut être relancé autant de fois que tu veux (après une mise à jour par exemple). Il n'utilise jamais
`sudo` et vérifie à la fin que tout marche pour de vrai : il arrête brutalement la surveillance pour voir si macOS la
relance, dépose un message de test dans iCloud et attend la réponse. Il compare aussi l'empreinte de tes autres
projets avant et après : ils ne doivent pas avoir bougé d'un octet.

Ensuite, il te reste quelques gestes (ajouter 2 raccourcis sur l'iPhone, relier Gmail) : **ACTIONS_HUMAINES.md**.

> **Le Nettoyeur de démarrage va te signaler une fois un nouvel élément** : `com.<ta session>.bouclier`.
> C'est normal : c'est la surveillance de Bouclier. Garde-le.

---

## Vérifier un message

### Sur l'iPhone

1. Fais une **capture d'écran** du message (bouton latéral + volume haut), touche la miniature en bas à gauche, puis
   **Partager** (en haut à droite). Pour un mail ou un lien : appui long → **Partager**.
2. Choisis **Arnaque ?**.
3. La réponse s'affiche en quelques secondes. Il faut que le Mac soit allumé et ta session ouverte : s'il dort,
   le raccourci affiche au bout d'une minute les 5 réflexes de base.

### Sur le Mac

- Sélectionne le texte, clic droit → **Services** → **Est-ce une arnaque ?**
- Ou un fichier (capture, mail `.eml`) dans le Finder : clic droit → **Actions rapides** → **Est-ce une arnaque ?**
- Ou dans le Terminal : `bouclier verifier "le texte du SMS"` ; `bouclier verifier --presse-papiers` pour le texte
  copié.

### Dans Gmail

Rien à faire : une fois Gmail relié (ACTIONS_HUMAINES.md), chaque nouveau mail de ta boîte de réception est vérifié.
Tu reçois une notification seulement pour une arnaque ou un message très suspect. Bouclier lit Gmail **en lecture
seule** : il ne marque rien comme lu, ne déplace rien, ne supprime rien.

### Lire la réponse

| | Ce que ça veut dire |
|---|---|
| 🔴 **Arnaque** | Ne clique pas, ne rappelle pas, ne réponds pas. Supprime le message. |
| 🟠 **Très suspect** | Fais comme si c'était une arnaque. Vérifie en allant toi-même sur l'appli ou le site officiels. |
| 🟡 **Prudence** | Quelques signes. Ne donne rien (code, carte, mot de passe) sans vérifier par toi-même. |
| ⚪ **Pas de signe d'arnaque détecté** | Rien d'inquiétant trouvé. Ce n'est pas une garantie : reste prudent. |

Chaque réponse dit **pourquoi** (« le lien mène à colissimo-livraison.top, pas à laposte.fr ») et **quoi faire**,
avec les bons numéros (17 Cyber, 33700 pour signaler un SMS…). Bouclier n'ouvre **jamais** un lien d'un message : il
lit seulement l'adresse. `bouclier historique` montre tes dernières vérifications (texte caviardé).

**Le coût** : l'analyse se fait d'abord sur ton Mac. Claude n'est consulté que si les règles hésitent, avec un
plafond de 2 $ par mois (après, analyse locale seule jusqu'au mois suivant). Ton nom, ton adresse, tes numéros sont
retirés du texte avant tout envoi.

---

## Lire ton inventaire de comptes

```
bouclier inventaire
bouclier comptes
```

Bouclier lit seulement l'**en-tête** des mails (expéditeur, sujet, date) et, dans Chrome, Brave, Edge, Arc et
Firefox, la **liste** des sites enregistrés. Il ne lit jamais un mot de passe. L'inventaire se refait tout seul
chaque semaine.

Pour chaque compte, décide (Bouclier n'agit jamais à ta place) :

```
bouclier compte deezer supprimer
bouclier compte deezer supprime
bouclier compte amazon garder
```

Le tableau de bord donne le lien direct de suppression de chaque compte quand il est connu (163 services français).

---

## Réagir à une fuite

Chaque jour, Bouclier télécharge la liste publique des fuites de [Have I Been Pwned](https://haveibeenpwned.com) et la
compare à ton inventaire. Si un site où tu as un compte a fuité **après** que tu y as créé ton compte, tu reçois une
notification, une seule fois par fuite. `bouclier fuites` les liste, avec les données touchées.

Quand ça arrive :

1. **Change le mot de passe de ce site**, et partout où tu as utilisé le même. L'app **Mots de passe** d'Apple te
   montre les mots de passe réutilisés ou fuités : ouvre-la → **Recommandations de sécurité**.
2. **Active la double authentification** sur ce compte.
3. **Méfie-toi des messages qui parlent de ce site** dans les semaines suivantes : les escrocs utilisent les données
   volées pour des arnaques ciblées.

**Vérifier ton adresse mail elle-même** (gratuit) : active la surveillance de
[Mozilla Monitor](https://monitor.mozilla.org) avec ton adresse. Bouclier ne le fait pas pour toi (il faudrait une clé
payante de Have I Been Pwned ; si tu en as une, mets-la dans `config.toml`, rubrique `[fuites]`).

---

## Nettoyer une photo avant de l'envoyer

Une photo de l'iPhone contient souvent l'endroit exact où elle a été prise, l'appareil et la date.

- **Sur l'iPhone** : Partager → **Envoyer sans traces** (tout se fait sur l'iPhone).
- **Sur le Mac** : clic droit sur la photo ou le document → **Actions rapides** → **Nettoyer les métadonnées**.
- Ou : `bouclier nettoyer photo.jpg`

Tu obtiens une copie `photo (propre).jpg` à côté de l'original, qui n'est **jamais** modifié. Les couleurs et la
qualité sont gardées, la photo est remise à l'endroit. Marche avec JPEG, HEIC, PNG, WebP, TIFF, PDF, Word, Excel,
PowerPoint, et les vidéos si `ffmpeg` est installé. `--remplacer` met l'original à la Corbeille (récupérable).

---

## La fiche urgence

```
bouclier urgence editer
bouclier urgence
```

`editer` ouvre un petit fichier où tu peux noter (si tu veux) tes contacts d'urgence et le numéro d'opposition de ta
banque. La fiche contient les numéros utiles **vérifiés sur les sites officiels** (15, 17, 18, 112, 114, 33700,
opposition carte bancaire, centre antipoison, Info Escroqueries, pharmacie de garde, 17Cyber…), et les réflexes en cas d'arnaque, de vol de carte ou de compte
piraté.

Tu obtiens :
- `Fiche urgence.pdf`, copiée dans **iCloud Drive/Bouclier** : garde-la téléchargée sur l'iPhone
  (ACTIONS_HUMAINES.md) pour la lire sans réseau ;
- une **carte A6** à imprimer et à glisser dans ton portefeuille ;
- une image pour ton **écran verrouillé**, si tu as noté des contacts.

Bouclier revérifie les numéros sur les sites officiels tous les 6 mois et te rappelle de relire ta fiche.

**Tes infos de santé** (allergies, traitements, groupe sanguin) n'ont pas leur place ici : mets-les dans la
**Fiche médicale** de l'app **Santé** de l'iPhone, lisible par les secours depuis l'écran verrouillé.

---

## Quand quelque chose ne va pas

```
bouclier doctor
```

Chaque brique est ✅ (marche), ⚠️ (marche en partie) ou ❌ (absente), avec la solution en une ligne. Les journaux
(caviardés) sont dans `~/Library/Logs/Bouclier/`.

---

## Ce que Bouclier ne fera jamais

- Ouvrir un lien trouvé dans un message (il lit seulement l'adresse, et demande au plus la date de création du nom de
  domaine).
- Lire un mot de passe (navigateurs, trousseau, export).
- Modifier ta boîte Gmail (marquer comme lu, déplacer, étiqueter, supprimer, se désabonner).
- Supprimer ou modifier un de tes fichiers.
- Contacter un autre site que : Claude, Have I Been Pwned, rdap.org, OpenPhish, URLhaus, les sites officiels
  (gouv.fr, service-public.fr, CHU, centres antipoison) et Gmail.

---

## Désinstaller

```
cd ~/Assistant/bouclier
./uninstall.sh
```

La surveillance, la commande `bouclier`, les actions rapides et l'élément de démarrage sont retirés. Tes données
(historique, inventaire, fiche) restent : `./uninstall.sh --tout` les retire aussi. Le dossier **iCloud
Drive/Bouclier** et les 2 raccourcis de l'iPhone restent : supprime-les à la main si tu veux.

---

Sources et licences : **CREDITS.md**. Choix techniques : **DECISIONS.md**.
