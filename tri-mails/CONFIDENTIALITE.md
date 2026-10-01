# Règles de confidentialité — « Tri mails »

« Tri mails » est une application **personnelle**, utilisée uniquement par la
personne qui l'a installée, sur son propre ordinateur, pour sa propre boîte Gmail.
Elle n'est ni vendue ni proposée au public.

## Ce que fait l'application

À chaque nouveau mail arrivé dans la boîte de réception, elle :

1. lit l'expéditeur, l'objet et un extrait du texte ;
2. demande à un modèle d'IA dans quel « bac » le ranger ;
3. pose l'étiquette Gmail correspondante et, pour les mails automatiques ou
   publicitaires, les archive (ils restent dans Gmail, hors de la boîte de réception).

## Où sont traitées les données

- Le programme tourne **uniquement sur l'ordinateur de son propriétaire**.
  Il n'existe aucun serveur « Tri mails ».
- Pour classer un mail, **l'expéditeur, l'objet et un extrait du texte**
  (1 500 caractères au maximum, jamais les pièces jointes) sont envoyés à
  l'API Claude d'Anthropic. Rien d'autre ne quitte l'ordinateur.
- Sont conservés **localement** : les identifiants des mails déjà traités et le
  bac choisi, pour ne jamais traiter deux fois le même mail.

## Ce que l'application ne fait jamais

- Elle ne supprime aucun mail et n'en met aucun à la corbeille.
- Elle n'envoie aucun mail.
- Elle ne revend, ne partage et ne publie aucune donnée.

## Révoquer l'accès

L'accès à Gmail se retire à tout moment sur
<https://myaccount.google.com/permissions> (ligne « Tri mails »).
