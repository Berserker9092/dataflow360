"""Dépendances FastAPI : authentification multi-tenant (X-Tenant-API-Key) et accès base."""

import time

from fastapi import Header, HTTPException, status

from src.storage.db_connection import get_pg_connection
from src.storage.tenants import hash_api_key

_CACHE_TTL = 60
_cache: dict[str, tuple[float, str]] = {}


def get_current_tenant(
    x_tenant_api_key: str | None = Header(default=None, alias="X-Tenant-API-Key"),
) -> str:
    """Renvoie le tenant_id (UUID) associé à la clé, ou 401."""
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé API Tenant invalide ou absente.")
    if not x_tenant_api_key or len(x_tenant_api_key) < 8:
        raise invalid
    key_hash = hash_api_key(x_tenant_api_key)
    cached = _cache.get(key_hash)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM tenants WHERE api_key_hash = %s", (key_hash,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise invalid
    _cache[key_hash] = (time.time(), str(row[0]))
    return str(row[0])


def get_db():
    conn = get_pg_connection()
    try:
        yield conn
    finally:
        conn.close()
