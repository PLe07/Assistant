"""Les catégories de données des fuites (Have I Been Pwned, en anglais) traduites en français simple."""

from __future__ import annotations

DONNEES = {
    "Email addresses": "adresses e-mail", "Passwords": "mots de passe", "Usernames": "identifiants",
    "Names": "noms", "Phone numbers": "numéros de téléphone", "Physical addresses": "adresses postales",
    "Dates of birth": "dates de naissance", "IP addresses": "adresses de connexion (IP)", "Genders": "sexe",
    "Geographic locations": "localisation", "Credit cards": "cartes bancaires",
    "Partial credit card data": "numéros de carte partiels", "Bank account numbers": "numéros de compte bancaire",
    "Social media profiles": "profils de réseaux sociaux", "Job titles": "métiers", "Employers": "employeurs",
    "Website activity": "activité sur le site", "Purchases": "achats", "Device information": "appareils utilisés",
    "Security questions and answers": "questions secrètes et leurs réponses", "Password hints": "indices de mot de passe",
    "Auth tokens": "jetons de connexion", "Government issued IDs": "pièces d'identité",
    "Passport numbers": "numéros de passeport", "Social security numbers": "numéros de sécurité sociale",
    "Salutations": "civilité", "Spoken languages": "langues parlées", "Time zones": "fuseaux horaires",
    "Account balances": "soldes de compte", "Income levels": "revenus", "Marital statuses": "situation familiale",
    "Education levels": "niveau d'études", "Ethnicities": "origines", "Religions": "religion",
    "Sexual orientations": "orientation sexuelle", "Health insurance information": "assurance santé",
    "Medical records": "dossiers médicaux", "Family members' names": "noms des proches",
    "Private messages": "messages privés", "Chat logs": "conversations", "Photos": "photos",
    "Browser user agent details": "navigateurs utilisés", "Avatars": "photos de profil",
    "Credit status information": "situation de crédit", "Payment histories": "historique des paiements",
    "Payment methods": "moyens de paiement", "Vehicle details": "véhicules", "Nationalities": "nationalité",
    "Historical passwords": "anciens mots de passe", "Cryptocurrency wallet addresses": "portefeuilles de cryptomonnaie",
    "Biometric data": "données biométriques", "Driver's licenses": "permis de conduire",
    "Customer interactions": "échanges avec le service client", "Homepage URLs": "sites personnels",
    "Instant messenger identities": "identifiants de messagerie", "Mothers maiden names": "nom de jeune fille de la mère",
    "Nicknames": "surnoms", "Occupations": "professions", "Personal descriptions": "descriptions personnelles",
    "Personal health data": "données de santé", "Political views": "opinions politiques",
    "Professional skills": "compétences professionnelles", "Reward program balances": "points de fidélité",
    "SMS messages": "SMS", "Support tickets": "demandes au support", "Travel habits": "habitudes de voyage",
    "Utility bills": "factures (énergie, eau)", "Years of birth": "années de naissance", "Ages": "âges",
    "Age groups": "tranches d'âge", "Email messages": "e-mails", "Home ownership statuses": "statut de logement",
    "Household income": "revenus du foyer", "Mobile numbers": "numéros de mobile", "Credit card CVV": "cryptogrammes de carte",
    "Bank account details": "coordonnées bancaires", "Financial transactions": "opérations financières",
    "Places of birth": "lieux de naissance", "Driver's license numbers": "numéros de permis de conduire",
}  # fmt: skip
SENSIBLES = frozenset({"Passwords", "Historical passwords", "Password hints", "Security questions and answers",
                       "Credit cards", "Credit card CVV", "Bank account numbers", "Bank account details",
                       "Auth tokens", "Government issued IDs", "Passport numbers", "Social security numbers"})  # fmt: skip


def traduire(donnees: list[str]) -> list[str]:
    return [DONNEES.get(d, d.lower()) for d in donnees]


def mots_de_passe_concernes(donnees: list[str]) -> bool:
    return any(d in ("Passwords", "Historical passwords", "Password hints") for d in donnees)
