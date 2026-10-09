"""Point d'entrée de l'API DataFlow360."""

import json
import logging
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import config
from src.api.routes import router, webhook_router
from src.api.routes_extra import extra_router

logging.basicConfig(level=logging.INFO, format="%(message)s")

if os.getenv("LOG_FILE"):
    logging.getLogger().addHandler(
        logging.FileHandler(os.getenv("LOG_FILE"))
    )

TAGS = [
    {
        "name": "webhook",
        "description": "Ingestion des événements de checkout (Mongo + Redis).",
    },
    {
        "name": "kpi",
        "description": "Indicateurs clés : CA, commandes, panier moyen, top produits.",
    },
    {
        "name": "stock",
        "description": "État des stocks et alertes de rupture.",
    },
    {
        "name": "fraud",
        "description": "Alertes de fraude temps réel et décisions.",
    },
    {
        "name": "forecast",
        "description": "Prévisions de ventes (XGBoost).",
    },
    {
        "name": "assistant",
        "description": "Assistant IA : recherche sémantique + LLM (RAG).",
    },
]

app = FastAPI(
    title="DataFlow360 API",
    description="SaaS analytics multi-tenant : toutes les routes exigent X-Tenant-API-Key.",
    version="1.0.0",
    openapi_tags=TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(router)
app.include_router(extra_router)


@app.get(
    "/health",
    tags=["webhook"],
    summary="Vérification de disponibilité",
)
def health():
    return {"status": "ok"}


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    logging.getLogger("api.access").info(
        json.dumps(
            {
                "path": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round(
                    (time.perf_counter() - start) * 1000,
                    1,
                ),
            }
        )
    )

    return response