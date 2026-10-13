# DataFlow360 - Groupe 1

Plateforme décisionnelle SaaS pour vendeurs e-commerce.

## Structure du projet

- `docs/` : Documentation technique et cahier des charges.
- `data/` : Jeux de données bruts et préparés (Olist).
- `src/ingestion/` : Scripts de nettoyage et pipelines ELT.
- `src/storage/` : Modèles de données PostgreSQL et scripts de migration.
- `src/batch/` : Scripts d'agrégation batch nocturne et calcul RFM.
- `src/streaming/` : Flux d'événements et alerte en quasi temps réel (Redis Streams).
- `src/ml/` : Modèles de prévision de la demande et scoring de fraude (XGBoost / scikit-learn).
- `src/rag/` : Assistant intelligent basé sur ChromaDB et LLM.
- `src/api/` : Application Backend FastAPI.
- `src/dashboard/` : Interface Frontend (Vue 3 / Streamlit).

## Démarrage rapide

```bash
docker-compose up --build
```
