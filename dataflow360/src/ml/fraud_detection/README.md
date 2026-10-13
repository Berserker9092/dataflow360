# Détection de fraude (module ML)

## Contenu
- `train.py` : entraîne 3 modèles (régression logistique, forêt aléatoire, XGBoost), choisit le meilleur sur la validation et enregistre `models/fraud_model.pkl`, avec 3 graphiques (images).
- `scoring.py` : charge le modèle et prédit le risque de fraude d'une commande.
- `models/` : créé par l'entraînement. Le `.pkl` n'est pas versionné (règle `*.pkl` du `.gitignore`).

## Générer le modèle
1. Installer les dépendances : `pip install -r requirements.txt`, puis `pip install matplotlib` si elle manque.
2. Placer les 3 fichiers de données dans ce dossier, sans les ajouter à Git : `checkout_events.csv`, `customers.csv`, `fraud.csv`.
3. Lancer : `python3 train.py`

Résultat : `models/fraud_model.pkl` et 3 images (courbes précision-recall, matrice de confusion, importance des variables).
Le modèle a été entraîné avec scikit-learn 1.9.1 : utiliser la même version pour le recharger.

## Utiliser le modèle
```python
from src.ml.fraud_detection.scoring import evaluer_evenement

resultat = evaluer_evenement(event, country_code="CI", velocity_count_60s=2)
```

- `event` : l'événement de l'API (`CheckoutEvent` de `schemas.py`) sous forme de dictionnaire.
- `country_code` : pays du client, à lire dans la table clients (via `customer_id`).
- `velocity_count_60s` : nombre de commandes du même client sur les 60 dernières secondes, commande en cours incluse.

Retour :
- `niveau` : `OK`, `A_VERIFIER` ou `ALERTE_FORTE`
- `alerte_vendeur` : `True` si le vendeur doit être alerté
- `probabilite` : score de risque (pas un vrai pourcentage)
- `raison` : texte à afficher au vendeur

## Conventions
- `day_of_week` : lundi = 0.
- `payment_source_country` vide : paiement cash (traité comme « AUCUN »).

## Limites
- Données simulées : les scores sont probablement plus élevés qu'en réel.
- `payment_status` peut valoir `pending` à la création de la commande, alors que le modèle a appris sur des statuts finaux.
- Le seuil de la zone grise (0,30) reste à valider sur les données de validation.
