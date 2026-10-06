# 🗂 Le Trieur

Tu envoies un document au Mac (depuis l'iPhone, le Finder ou un dossier) : il est lu, reconnu, renommé et rangé.
Une facture d'un objet durable ouvre sa fiche de garantie, avec des rappels avant la fin.

## Envoyer un document

- **iPhone** : Partager → « Envoie au Mac » (ou « Envoie au Mac + note » : « garantie 3 ans »).
- **Mac** : glisser dans `~/Desktop/À trier`, ou clic droit → Actions rapides → « Trier avec l'assistant ».
- **Téléchargements** : un PDF téléchargé est rangé tout seul si le Trieur est sûr de lui (sinon il ne bouge pas).
- **Terminal** : `python trieur.py ajouter facture.pdf`.

## Où ça va

`~/Documents/Classés/` : `Factures/2026/2026-10-03_Fnac_Facture_Casque-Sony_249,99€.pdf`, `Banque/…`, `Impôts/…`,
`Santé/…`. Ce qu'il ne sait pas classer : `Classés/À vérifier`. Les photos de vacances : `~/Pictures/Depuis l'iPhone`.
Tes garanties : `Classés/Garanties` (des alias) et `iCloud Drive/BoiteMac/Mon coffre.html` (lisible sur l'iPhone).

## Une erreur ?

```
python trieur.py journal
python trieur.py corriger 12 --type devis
python trieur.py annuler 12
```
`corriger` range au bon endroit et retient la leçon pour cet émetteur. `annuler` remet l'original à sa place.

## Ta vie privée

Tout se fait sur le Mac. Claude n'est consulté que si les règles hésitent, et ne reçoit qu'un extrait du texte,
caviardé (IBAN, numéros, adresses, ton nom…). Santé, identité, impôts et paie ne partent jamais.

## Pour aller plus loin

`python trieur.py` (toutes les commandes), `python trieur.py doctor` (la santé), `regles.toml` (les règles, à
compléter), DECISIONS.md (les choix), RAPPORT_FINAL.md (les preuves).
