# Prévision hebdomadaire de la demande par produit

Module : `src/ml/demand_forecast/` (même organisation que `fraud_detection` : `train.py` entraîne, `predict.py` sert)

- `train.py` : lit les ventes dans PostgreSQL, compare le modèle à des méthodes simples (backtest), entraîne le modèle final et le sauvegarde dans `models/forecast_<tenant>.pkl`. Contient aussi `retrain()`, appelable par un job planifié.
- `predict.py` : charge le modèle, lit les ventes à jour et écrit les prévisions. Contient `get_forecast()`, appelable par le backend ou le dashboard.

Ce script prévoit, pour **chaque produit**, le nombre d'**unités qui seront vendues pendant les 4 prochaines semaines**. Il sert à anticiper les ruptures de stock (objectif du cahier des charges : « prévoir la demande produit »).

## En une image

```
PostgreSQL (orders + order_items + products du tenant)
        │  1. load_weekly      : lit la base, garde les semaines complètes, compte les unités vendues
        ▼
Tableau U : 1 ligne par produit (8 000) x 1 colonne par semaine (142)  = unités vendues
        │  2. build_features   : pour chaque (produit, semaine t), résume le passé (ventes récentes, cumuls…)
        ▼
Table d'apprentissage : features (entrées) + cible (unités vendues à la semaine t+h)
        │  3. XGBoost (perte de Poisson) : un modèle par horizon h = 1, 2, 3, 4 semaines
        ▼
4. Backtest sur les 13 dernières semaines  → comparaison avec des méthodes simples (baselines)
5. Entraînement final sur tout l'historique → models/forecast_<tenant>.pkl          (train.py)
        ▼
6. predict.py : charge le modèle + ventes à jour → prévision des 4 semaines à venir
        ▼
forecast_products_weekly.csv  +  forecast_products_summary.csv
```

## Lancer

Les données sont lues **dans le data warehouse PostgreSQL de l'équipe** (guide, étape 58), pas dans les CSV.

**1. Préparer la base** (une fois) : démarrer Postgres avec le `docker-compose.yml` du dépôt, puis laisser l'ETL de Data Engineering remplir les tables pour le tenant `tenant_demo` (le script s'arrête avec un message clair si le tenant n'existe pas ou n'a aucune commande).

```bash
docker compose up -d postgres
docker compose ps            # le service doit être "healthy"
```

**2. Entraîner puis prévoir**, depuis la racine du code (le dossier qui contient `src/`) :

```bash
python -m src.ml.demand_forecast.train --host localhost --port 5433 --password <mdp>     # entraînement + backtest
python -m src.ml.demand_forecast.train --host localhost --port 5433 --password <mdp> --fast   # plus rapide
python -m src.ml.demand_forecast.predict --host localhost --port 5433 --password <mdp>   # prévisions
python -m src.ml.demand_forecast.train --no-backtest ...  # ré-entraînement seul (job de nuit)
python -m src.ml.demand_forecast.train --data-dir data/raw  # mode CSV, hors base (tests sans Docker)
python -m src.ml.demand_forecast.train --help               # toutes les options
```

Sans `--host`, les scripts utilisent `get_pg_connection()` (`src/storage/db_connection.py`), donc la même configuration que le reste du projet. Le port est 5432 dans le compose du dépôt (5433 sur le poste d'Ousmane : `--port 5433`).

| Option | Rôle | Défaut |
|---|---|---|
| `--source` | `db` (PostgreSQL) ou `csv` | `db`, ou `csv` si `--data-dir` est donné |
| `--tenant` | nom du tenant dans la table `tenants` (sert aussi à nommer le modèle) | `tenant_demo` |
| `--host`, `--port`, `--db`, `--user`, `--password` | connexion explicite (sinon `get_pg_connection()`) | `POSTGRES_PORT` ou 5432, `dataflow360`, `dataflow` |
| `--data-dir` | dossier des CSV (mode CSV seulement) | `data/raw` |
| `--statuses` | `all` = toutes les commandes sauf annulées/échouées, ou une liste (`delivered,shipped`) | `all` |
| `--horizon` | nombre de semaines à prévoir (train) | 4 |
| `--test-weeks` | nombre de dernières semaines réservées au test | 13 |
| `--fast` | raccourci : 100 arbres, une origine d'entraînement sur deux | désactivé |
| `--no-backtest` | entraîne seulement, sans comparaison aux baselines (plus rapide) | désactivé |
| `--trees`, `--lr`, `--stride` | réglages fins de vitesse | 300, 0.05, 1 |
| `--out-dir`, `--processed-dir` | dossiers de sortie | `models`, `data/processed` |

Dépendances : `pandas`, `numpy`, `joblib`, `xgboost`, et `psycopg` (déjà utilisé par le projet) pour lire la base.

**Ce que le script lit** : `tenants` (pour retrouver le tenant), `orders` (statut, date), `order_items` (produit, `quantity`) et `products` (catégorie, `product_cost`). La table `products` du warehouse n'a pas de prix de vente : `product_cost` sert de proxy pour la variable `log_price`. Si `quantity` manque dans `order_items`, une ligne de commande compte pour une unité (avertissement affiché).

## Utiliser depuis un autre module

```python
from src.ml.demand_forecast.train import retrain          # ex. dans src/batch/nightly_jobs.py (étape 43 du guide)
from src.ml.demand_forecast.predict import get_forecast   # ex. backend ou dashboard (étape 82)

retrain(tenant="tenant_demo", host="localhost", port=5433, password="...")
forecast, summary = get_forecast(tenant="tenant_demo", host="localhost", port=5433, password="...")
```

`forecast` : une ligne par produit et par semaine (`tenant_id`, `product_id`, `category`, `week_start`, `horizon`, `predicted_units`). `summary` : une ligne par produit.

## Lire le code, fonction par fonction

| Fonction | Ce qu'elle fait |
|---|---|
| `connect_db`, `_read_db` | Se connecte à PostgreSQL et agrège en SQL les unités vendues par produit et par semaine pour le tenant (`DATE_TRUNC('week', …)`, commandes annulées/échouées exclues). `_read_csv` fait la même chose depuis les CSV. |
| `load_weekly` | Choisit la source, ne garde que les **semaines complètes** (lundi à dimanche) et construit la matrice `U` (produits x semaines). Une semaine sans vente vaut 0. |
| `build_features` | Pour chaque produit et chaque semaine d'origine `t`, calcule les variables d'entrée **avec ce qu'on savait à la fin de la semaine t uniquement** (aucune fuite du futur), et la cible : les unités vendues à `t + h`. |
| `new_model` | Crée le XGBoost avec la perte `count:poisson`, adaptée aux comptages (0, 1, 2…) avec beaucoup de zéros. |
| `rmse`, `wape`, `poisson_dev` | Les métriques de comparaison (voir plus bas). |
| `encode_categories` | Transforme la catégorie en nombre. L'ordre appris est sauvegardé avec le modèle, pour que `predict.py` utilise les mêmes codes. |
| `main` (train) | Enchaîne : backtest, entraînement final sur tout l'historique, sauvegarde du modèle. |
| `retrain` | Lance `main` sans backtest : à appeler depuis un job planifié. |
| `load_model`, `forecast_from_model` (predict) | Chargent le modèle et prévoient les semaines à venir pour chaque produit, à partir des ventes à jour. |
| `get_forecast`, `main` (predict) | Interface pour les autres modules, et commande qui écrit les deux fichiers CSV. |

Pourquoi `argparse` et `pathlib` : `argparse` lit les options tapées dans le terminal (`--horizon 4`), `pathlib` construit les chemins de fichiers de façon portable.

## La cible et les variables d'entrée

**Cible** : le nombre d'unités vendues par un produit pendant la semaine `t + h` (un modèle pour chaque `h` de 1 à 4).

**15 variables**, toutes calculées à la fin de la semaine `t` :

| Groupe | Variables | Sens |
|---|---|---|
| Ventes récentes | `lag0`, `lag1`, `lag2`, `lag3` | unités vendues cette semaine et les 3 précédentes |
| Cumuls | `sum4`, `sum13`, `sum26` | unités vendues sur 4, 13, 26 semaines |
| Niveau du produit | `rate_all`, `cum_units` | vente moyenne par semaine, total depuis le début |
| Régularité | `weeks_since_sale`, `n_sale_weeks_26` | semaines depuis la dernière vente, nombre de semaines avec vente sur 26 |
| Produit | `cat_code`, `log_price` | catégorie, prix (logarithme) |
| Calendrier | `target_woy`, `target_month` | semaine de l'année et mois de la semaine à prévoir |

## Pourquoi cette méthode

- **Un seul modèle pour tous les produits** : un produit n'a qu'une vingtaine de ventes sur toute la période, trop peu pour un modèle individuel.
- **Perte de Poisson** : environ 93 % des couples produit-semaine valent 0. Une perte classique prédirait presque toujours 0.
- **Prévision directe** (un modèle par horizon) plutôt que récursive : les erreurs ne s'accumulent pas.
- **Hebdomadaire** : le niveau journalier est encore plus creux.

## Validation

Les 13 dernières semaines servent de test, jamais vues à l'entraînement. Le modèle est comparé à :

- **zéro** (toujours 0) ;
- **moyenne historique** du produit ;
- **moyenne des 13 dernières semaines** (équivalent hebdomadaire de la moyenne mobile demandée par le guide).

Métriques affichées :

- **RMSE** et **déviance de Poisson** : récompensent une bonne estimation de la moyenne, adaptées aux comptages creux. Plus bas = mieux.
- **MAE** : le critère littéral de l'étape 60 du guide. Elle est affichée, avec le verdict « respecté / non respecté », mais elle est trompeuse ici : avec 93 % de zéros, prévoir 0 partout donne la meilleure MAE.
- **WAPE agrégé par catégorie et par semaine** : l'échelle où une prévision est lisible.
- **Classement des produits** : part de la demande réelle des 4 semaines suivantes captée par les 5 % de produits les mieux classés (5 % = hasard), à partir d'une seule origine pour éviter toute fuite.

Le verdict final est gradué : moins bon, équivalent (gain < 1 %), légèrement meilleur (1 à 5 %) ou nettement meilleur (> 5 %).

## Résultats sur le dataset (exécution du 10 octobre 2026, données lues dans PostgreSQL, option `--fast`)

8 000 produits, 142 semaines complètes (du 2024-01-01 au 2026-09-14), 132 734 unités, 93,5 % de produit-semaines à 0.

| | RMSE | Déviance de Poisson |
|---|---|---|
| Zéro | 0,547 | n/a |
| Moyenne historique | 0,536 | 0,700 |
| Moyenne 13 semaines | 0,555 | 1,105 |
| **Modèle XGBoost** | **0,534** | **0,682** |

- Gain du modèle sur la meilleure baseline : **+0,3 % en RMSE, +2,7 % en déviance**, soit un modèle **équivalent** à la moyenne historique.
- MAE (critère littéral du guide) : le modèle bat la moyenne sur 13 semaines (0,219 contre 0,220), mais « toujours 0 » fait mieux (0,118) : la MAE n'est pas un bon critère ici.
- Erreur agrégée par catégorie et par semaine : environ 10,7 % (10,9 % pour la moyenne sur 13 semaines).
- Classement des produits : modèle 4,6 %, moyenne 13 semaines 4,0 %, moyenne historique 4,8 %, contre 5 % au hasard.

**Lecture** : dans ce jeu de données synthétique, les ventes d'un produit une semaine donnée sont presque aléatoires et dépendent à peine de ses ventes passées. Le modèle ne fait pas mieux qu'une moyenne bien calculée. La prévision n'est vraiment utile qu'agrégée (par catégorie, ou sur plusieurs semaines).

## Fichiers produits

- (`predict.py`) `data/processed/forecast_products_weekly.csv` : colonnes `tenant_id`, `product_id`, `category`, `week_start`, `horizon`, `predicted_units` (nombre décimal : demande attendue).
- `data/processed/forecast_products_summary.csv` : une ligne par produit (colonne `category`), avec `predicted_4w` (demande prévue sur 4 semaines), `sold_last_26w` et `weeks_of_cover` (stock divisé par la demande hebdomadaire prévue).
- (`train.py`) `models/forecast_<tenant>.pkl` : les modèles entraînés (un par horizon), avec la liste des variables, l'ordre des catégories et la dernière semaine d'entraînement. Les dossiers `models/` et `data/` sont ignorés par Git.

## Conformité au cahier des charges (guide, étapes 58 à 61 et 82)

| Exigence | État |
|---|---|
| XGBoost comme algorithme unique (étape 59) | Respecté. Hyperparamètres différents du guide (300 arbres, profondeur 5, perte de Poisson) car adaptés aux comptages creux. |
| Comparaison à une base simple (étape 60) | Respecté dans l'esprit. Comparaison à des moyennes, avec la MAE du guide affichée en plus du RMSE et de la déviance. |
| Sauvegarde dans `models/` avec le tenant dans le nom (étape 61) | Respecté : `models/forecast_<tenant>.pkl`. |
| Granularité par produit | Respecté, au pas hebdomadaire plutôt que journalier (ventes trop rares). |
| Cible | Unités vendues, cohérent avec `forecasts.predicted_units` et l'étape 82, au lieu de `revenue_xof` (étape 58). |
| Source des données : PostgreSQL, pas les CSV (étape 58) | Respecté : lecture du warehouse, filtrée par tenant. Le mode CSV n'est qu'un secours pour tester sans Docker. Pas de prix de vente dans le warehouse : `product_cost` en proxy. |
| Écriture dans la table `forecasts` (tenant, produit, date, unités entières) | **À faire.** Pour l'instant : CSV. La table attend des unités entières, alors que la demande hebdomadaire par produit est souvent inférieure à 1. |
| Ré-entraînement nocturne par `nightly_jobs.py` (étape 43) | **Prêt à brancher** : `retrain()` fait le ré-entraînement sans backtest. Il reste à l'appeler depuis `nightly_jobs.py` avec APScheduler (fichier vide pour l'instant). |
| Graphique historique + prévision du dashboard (étape 82) | **À faire** : le dashboard doit lire le fichier de prévision (colonne `week_start`) ou la table. |
| Multi-tenant | Les lectures sont filtrées par `tenant_id` ; un tenant à la fois (`--tenant`). |

## Limites

- Ces résultats viennent d'un jeu de données synthétique sans saisonnalité marquée.
- Avec un petit catalogue (quelques dizaines de produits), un modèle global manque de données et une moyenne historique fait mieux.
- Les prévisions ne sont fiables qu'agrégées. Pour décider d'un réapprovisionnement, utiliser `predicted_4w` et `weeks_of_cover`.