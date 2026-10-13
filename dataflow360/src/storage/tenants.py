import hashlib

def hash_api_key(api_key: str) -> str:
    """Fonction de hachage simple pour débloquer les tests de l'API."""
    if not api_key:
        return ""
    return hashlib.sha256(api_key.encode()).hexdigest()

def resolve_tenant_id(conn, tenant_name: str | None = None) -> str:
    """Récupère l'UUID du tenant par son nom (ou depuis .env)."""
    import os
    name = tenant_name or os.getenv("TENANT_NAME", "Boutique démo")
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id FROM tenants WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"Tenant introuvable : {name}")
        return str(row[0])
