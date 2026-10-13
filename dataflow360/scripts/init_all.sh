#!/bin/bash
# =============================================================================
# DataFlow360 — Initialisation complète de la base
# =============================================================================
# Exécuté par le service "init" de docker-compose au démarrage.
# - Charge les CSV dans MongoDB
# - Transforme Mongo → Postgres (ETL)
# - Ajoute les noms clients
# - Entraîne le modèle XGBoost (prévisions)
# - Insère les prévisions dans Postgres
# - Indexe les documents RAG (assistant IA)
# =============================================================================

set -e

echo ""
echo "========================================================"
echo "  DataFlow360 — Initialisation"
echo "========================================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Charger les CSV dans MongoDB
# ---------------------------------------------------------------------------
echo "[1/6] Chargement CSV → MongoDB..."
if python -m src.ingestion.load_raw_mongo --dir data/raw; then
    echo "  ✅ CSV chargés dans MongoDB"
else
    echo "  ⚠️  Erreur CSV → Mongo (ignoré)"
fi

# ---------------------------------------------------------------------------
# 2. Transformer MongoDB → PostgreSQL (ETL)
# ---------------------------------------------------------------------------
echo ""
echo "[2/6] ETL MongoDB → PostgreSQL..."
if python -m src.ingestion.elt_pipeline; then
    echo "  ✅ ETL terminé"
else
    echo "  ⚠️  Erreur ETL (ignoré)"
fi

# ---------------------------------------------------------------------------
# 3. Ajouter les noms clients
# ---------------------------------------------------------------------------
echo ""
echo "[3/6] Génération des noms clients..."
if python -m src.ingestion.seed_customer_names 2>/dev/null; then
    echo "  ✅ Noms clients générés"
else
    echo "  ⚠️  Erreur seed clients (ignoré)"
fi

# ---------------------------------------------------------------------------
# 4. Entraîner le modèle XGBoost (prévisions)
# ---------------------------------------------------------------------------
echo ""
echo "[4/6] Entraînement XGBoost (peut prendre 2-5 min)..."
TENANT=$(grep TENANT_NAME .env | cut -d'=' -f2 | tr -d ' ')
if python -m src.ml.demand_forecast.train --tenant "$TENANT" --horizon 14 --fast; then
    echo "  ✅ Modèle XGBoost entraîné"
else
    echo "  ⚠️  Erreur XGBoost (ignoré)"
fi

# ---------------------------------------------------------------------------
# 5. Insérer les prévisions dans Postgres
# ---------------------------------------------------------------------------
echo ""
echo "[5/6] Insertion des prévisions..."
if python -m src.ml.demand_forecast.insert_forecasts 2>/dev/null; then
    echo "  ✅ Prévisions insérées"
else
    echo "  ⚠️  Erreur insertion prévisions (ignoré)"
fi

# ---------------------------------------------------------------------------
# 6. Indexer les documents RAG (assistant IA)
# ---------------------------------------------------------------------------
echo ""
echo "[6/6] Indexation RAG (peut prendre 2-5 min)..."
if python -m src.rag.indexer --tenant "$TENANT" --max 2000 2>/dev/null; then
    echo "  ✅ RAG indexé"
else
    echo "  ⚠️  Erreur RAG (ignoré, vérifier la clé Gemini)"
fi

echo ""
echo "========================================================"
echo "  ✅ Initialisation terminée"
echo "========================================================"
echo ""
