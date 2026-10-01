import os
import json
import redis
from fastapi import FastAPI, Header, HTTPException, status, Depends
from pydantic import BaseModel

app = FastAPI(title="DataFlow360 API")

# Connexion Redis (pour l'étape 21)
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)

async def get_current_tenant(
    x_tenant_api_key: str | None = Header(default=None, alias="X-Tenant-API-Key")
):
    if not x_tenant_api_key or len(x_tenant_api_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API Tenant invalide ou absente.",
        )
    # Vérification réelle contre la table tenants (clé hachée) : ajoutée à l'étape 56
    return x_tenant_api_key

@app.post("/webhook/order-created")
async def receive_checkout_event(
    event: dict,
    tenant_id: str = Depends(get_current_tenant),
):
    payload = event
    payload["tenant_id"] = tenant_id
    r.xadd("checkout_events", {"data": json.dumps(payload)}, maxlen=100_000, approximate=True)
    return {"status": "received", "tenant_id": tenant_id}