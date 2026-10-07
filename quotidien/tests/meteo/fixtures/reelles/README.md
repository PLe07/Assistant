# Captures réelles d'Open-Meteo

Ce dossier reçoit, **sur ton Mac**, une vraie réponse d'Open-Meteo prise par `install.sh`
(`quotidien meteo --capturer`), anonymisée (coordonnées arrondies au dixième, rien d'autre de personnel dedans).
`tests/meteo/test_open_meteo.py` et `tests/e2e_mac` la relisent avec toute la chaîne météo.

Le conteneur de construction n'a pas accès à Open-Meteo (pare-feu de l'environnement, DECISIONS D-06) : les fichiers
`*.json` d'ici ne sont pas versionnés.
