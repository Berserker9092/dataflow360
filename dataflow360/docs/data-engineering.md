# DataFlow360 — Documentation Data Engineering

## 1. Introduction

Cette documentation présente le travail réalisé sur la partie **Data Engineering** du projet DataFlow360.

L’objectif est de mettre en place une chaîne de traitement permettant de récupérer les données brutes, de les stocker, de les nettoyer et de les charger dans une base PostgreSQL destinée à l’exploitation analytique.

Le travail a été réalisé sur la branche .

## 2. Architecture Data Engineering

Le pipeline mis en place suit l’architecture suivante :

CSV → data/raw/ → MongoDB → Polars → PostgreSQL

MongoDB joue le rôle de **Landing Zone** pour conserver les données brutes.

Polars est utilisé pour le nettoyage et la transformation des données.

PostgreSQL constitue le **Data Warehouse** destiné à l’exploitation des données nettoyées et structurées.

## 3. Technologies utilisées

- Python
- MongoDB
- PostgreSQL
- pgvector
- Polars
- PyMongo
- psycopg
- Docker
- Docker Compose
- Git
- GitHub
## 4. Dataset

Le dataset DataFlow360 contient 11 fichiers CSV.

- customers.csv : 30 000 lignes
- products.csv : 8 000 lignes
- product_categories.csv : 25 lignes
- orders.csv : 50 000 lignes
- order_items.csv : 86 971 lignes
- order_payments.csv : 50 000 lignes
- order_reviews.csv : 18 017 lignes
- checkout_events.csv : 51 490 lignes
- fraud_ground_truth.csv : 50 000 lignes
- support_tickets.csv : 6 016 lignes
- geolocation.csv : 4 000 lignes

Le fichier fraud_ground_truth.csv est réservé à l’entraînement et à l’évaluation du système de détection de fraude. Il n’est pas utilisé comme source d’arrivée des données en temps réel.

## 5. Configuration Docker et PostgreSQL

L’environnement de développement utilise Docker Compose.

Le port 5432 étant déjà utilisé par PostgreSQL en local, PostgreSQL Docker a été exposé sur le port 5433.

Configuration :

- Host : localhost
- Port : 5433
- Database : dataflow360
- User : dataflow

L’image PostgreSQL utilisée est pgvector/pgvector:pg16.

Elle permet notamment d’utiliser l’extension vector nécessaire aux fonctionnalités liées au RAG.
## 6. Chargement des données brutes dans MongoDB

Le script src/ingestion/load_raw_mongo.py est responsable du chargement initial des fichiers CSV présents dans data/raw/.

Pour chaque fichier :

1. Une collection MongoDB correspondant au fichier est utilisée.
2. Les anciennes données du tenant sont supprimées.
3. Les lignes CSV sont lues.
4. Les métadonnées sont ajoutées.
5. Les documents sont insérés par lots.

Chaque document reçoit notamment :

- tenant_id
- _source_file
- _ingested_at

Le chargement est donc rejouable pour le tenant concerné.

## 7. Résultat du chargement MongoDB

Les 11 fichiers CSV ont été chargés avec succès dans MongoDB.

- checkout_events : 51 490 documents
- customers : 30 000 documents
- fraud_ground_truth : 50 000 documents
- geolocation : 4 000 documents
- order_items : 86 971 documents
- order_payments : 50 000 documents
- order_reviews : 18 017 documents
- orders : 50 000 documents
- product_categories : 25 documents
- products : 8 000 documents
- support_tickets : 6 016 documents

La présence des métadonnées du tenant a également été vérifiée.

## 8. Nettoyage et transformation avec Polars

Le nettoyage est réalisé dans src/ingestion/clean_olist.py.

Polars est utilisé pour effectuer les transformations avant le chargement dans PostgreSQL.

### Nettoyage des commandes

La fonction clean_orders() effectue notamment :

- suppression des doublons selon order_id ;
- suppression des lignes sans order_id ou customer_id ;
- conversion de order_purchase_timestamp en datetime ;
- conversion de order_total_amount en entier ;
- sélection des colonnes nécessaires.

Résultat :

- Avant nettoyage : 50 000 lignes
- Après nettoyage : 50 000 lignes

### Nettoyage des produits

La fonction clean_products() permet notamment de :

- supprimer les doublons selon product_id ;
- supprimer les produits sans identifiant ;
- convertir les champs numériques ;
- renommer la catégorie ;
- sélectionner les colonnes nécessaires.

## 9. Gestion du stock

La fonction stock_status() détermine l’état du stock à partir de la quantité disponible et du seuil d’alerte.

La logique appliquée est la suivante :

- stock_quantity = 0 → RUPTURE
- stock_quantity <= stock_alert_threshold → ALERTE
- stock_quantity > stock_alert_threshold → OK

Cette transformation permet de convertir une quantité brute en un état directement exploitable par les autres composants du projet.

Cette logique pourra notamment être utilisée par le dashboard et par les traitements temps réel.

## 10. Schéma PostgreSQL

Le fichier src/storage/schema.sql définit 9 tables principales :

- tenants
- customers
- products
- orders
- order_items
- fraud_ground_truth
- fraud_decisions
- rag_documents
- forecasts

L’extension vector est activée dans PostgreSQL afin de permettre le stockage de vecteurs pour les fonctionnalités liées au RAG.

Le schéma a été exécuté avec succès et les 9 tables ont été vérifiées dans PostgreSQL.

Les relations entre les tables utilisent notamment des clés primaires et des clés étrangères afin de garantir la cohérence des données.

## 11. Pipeline ETL

Le pipeline principal est situé dans src/ingestion/elt_pipeline.py.

Son fonctionnement est le suivant :

MongoDB
↓
Extraction
↓
Polars DataFrame
↓
Nettoyage et transformation
↓
PostgreSQL

Les données sont extraites des collections MongoDB puis transformées avec Polars avant leur chargement dans PostgreSQL.

Les fonctions principales actuellement mises en place sont :

- extract()
- get_tenant_uuid()
- load_customers()
- load_products()
- load_orders()

Le chargement PostgreSQL utilise le tenant correspondant afin de maintenir l’isolation des données.


## 12. Gestion du tenant

Le projet prévoit une architecture multi-tenant afin de pouvoir isoler les données de différents clients.

Pour les tests et le chargement initial, le tenant utilisé est :

tenant_demo

Un UUID est associé à ce tenant dans PostgreSQL.

Lors du chargement des données, cet identifiant est ajouté aux différentes tables afin d’associer chaque donnée à son tenant.

Cette approche permet de préparer l’architecture à une future utilisation multi-tenant du système.

## 13. Chargement PostgreSQL

Les fonctions de chargement principales mises en place sont :

- load_customers()
- load_products()
- load_orders()

Le chargement des commandes a été testé avec succès.

Résultats de la vérification :

- Nombre de commandes chargées : 50 000
- Nombre d’order_id uniques : 50 000

Les commandes sont associées au tenant PostgreSQL correspondant.

Le pipeline utilise une transaction PostgreSQL afin de pouvoir annuler les modifications en cas d’erreur lors du chargement.


## 14. Problèmes rencontrés et solutions

### Port PostgreSQL déjà utilisé

Le port 5432 était déjà utilisé par une instance PostgreSQL locale.

Solution : le conteneur PostgreSQL a été exposé sur le port 5433 de la machine hôte, tout en conservant le port 5432 à l’intérieur du conteneur.

### Extension vector indisponible

L’image PostgreSQL initialement utilisée ne permettait pas d’utiliser correctement l’extension vector.

Solution : utilisation de l’image pgvector/pgvector:pg16.

### Polars manquant

Polars n’était pas installé dans l’environnement Python.

Solution : ajout de la dépendance polars dans requirements.txt.

### Driver PostgreSQL manquant

Le pipeline nécessitait un driver Python pour communiquer avec PostgreSQL.

Solution : ajout de psycopg dans requirements.txt.

### Tenant PostgreSQL absent

Le pipeline avait besoin d’un tenant existant dans PostgreSQL pour associer les données.

Solution : création du tenant tenant_demo et récupération de son UUID lors des chargements.



## 15. Vérifications effectuées

Plusieurs vérifications ont été réalisées afin de valider le fonctionnement de la chaîne Data Engineering.

### Vérifications techniques

- compilation des scripts Python ;
- connexion à PostgreSQL ;
- connexion à MongoDB ;
- validation de la configuration Docker Compose ;
- vérification de l’extension vector ;
- vérification de la présence des 11 fichiers CSV.

### Vérifications MongoDB

- chargement des 11 fichiers CSV ;
- vérification du nombre de documents par collection ;
- vérification de la présence du tenant_id ;
- vérification des métadonnées d’ingestion.

### Vérifications PostgreSQL

- exécution du schéma ;
- présence des 9 tables ;
- connexion à la base ;
- nettoyage des commandes ;
- nettoyage des produits ;
- chargement des commandes ;
- vérification de l’unicité des order_id.

Résultat important :

50 000 commandes ont été chargées dans PostgreSQL et les 50 000 order_id sont uniques.


## 16. Git et GitHub

Le travail Data Engineering a été réalisé sur la branche :

feature/data-engineering

Le commit principal est :

03f93d4 — feat: implement data engineering ingestion and ETL

Ce commit contient notamment :

- le pipeline d’ingestion MongoDB ;
- le nettoyage avec Polars ;
- le pipeline ETL ;
- le schéma PostgreSQL ;
- la configuration PostgreSQL ;
- les dépendances nécessaires.

Le travail a été poussé sur le dépôt GitHub du projet afin de permettre son intégration avec les autres branches de l’équipe.



## 17. Rôle du Data Engineer

La partie Data Engineering réalisée comprend :

- préparation de l’environnement de données ;
- configuration de MongoDB ;
- configuration de PostgreSQL ;
- mise en place de la Landing Zone ;
- ingestion des données brutes ;
- ajout des métadonnées d’ingestion ;
- nettoyage des données ;
- transformation avec Polars ;
- conception du schéma PostgreSQL ;
- chargement des données dans PostgreSQL ;
- gestion du tenant ;
- vérification de la qualité des données ;
- résolution des problèmes techniques ;
- documentation du travail ;
- versionnement avec Git et GitHub.

Cette partie constitue la base de données sur laquelle les autres composants du projet pourront s’appuyer.

## 18. Évolutions futures

La base Data Engineering mise en place pourra être étendue avec les composants suivants :

- chargement complet des commandes et de leurs détails ;
- intégration des paiements et des avis clients ;
- traitement des événements en temps réel ;
- Redis Streams ;
- détection de fraude ;
- gestion dynamique du stock ;
- prévisions de la demande ;
- RAG ;
- API ;
- dashboard ;
- orchestration ;
- monitoring.

Ces fonctionnalités pourront s’appuyer sur l’architecture Data Engineering déjà mise en place.


## 19. Conclusion

La base Data Engineering de DataFlow360 est fonctionnelle.

Le pipeline permet désormais de suivre le flux suivant :

CSV
↓
MongoDB / Landing Zone
↓
Extraction
↓
Polars
↓
Nettoyage et transformation
↓
PostgreSQL / Data Warehouse

Cette architecture constitue une base solide pour intégrer progressivement les composants temps réel, Machine Learning, RAG, API et dashboard du projet.

La branche feature/data-engineering contient le travail Data Engineering réalisé et peut servir de base pour la poursuite de l’intégration avec les autres parties du projet.
