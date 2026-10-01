import os
import json
import redis
from fastapi import FastAPI, Header, HTTPException, status, Depends
from pymongo import MongoClient
from src.api.schemas import CheckoutEvent

app = FastAPI(title="DataFlow360 API")

# Connexion Redis
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)

# Connexion MongoDB (Zone Landing)
mongo_client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
mongo_db = mongo_client[os.getenv("MONGO_DB", "dataflow_raw")]

async def get_current_tenant(
    x_tenant_api_key: str | None = Header(default=None, alias="X-Tenant-API-Key")
):
    if not x_tenant_api_key or len(x_tenant_api_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API Tenant invalide ou absente.",
        )
    # Vérification réelle contre la table tenants (ajoutée à l'étape 56)[cite: 1]
    return x_tenant_api_key

@app.post("/webhook/order-created")
async def receive_checkout_event(
    event: CheckoutEvent,
    tenant_id: str = Depends(get_current_tenant),
):
    payload = event.model_dump()
    payload["tenant_id"] = tenant_id

    # 1) Écriture immédiate dans MongoDB (Zone Landing)[cite: 1]
    mongo_db["checkout_events"].insert_one({**payload})

    # 2) Publication dans Redis Streams pour le scoring temps réel[cite: 1]
    r.xadd("checkout_events", {"data": json.dumps(payload)}, maxlen=100_000, approximate=True)

    return {"status": "received", "tenant_id": tenant_id, "order_id": event.order_id}