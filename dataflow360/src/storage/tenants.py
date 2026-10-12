import hashlib

def hash_api_key(api_key: str) -> str:
    """Fonction de hachage simple pour débloquer les tests de l'API."""
    if not api_key:
        return ""
    return hashlib.sha256(api_key.encode()).hexdigest()
