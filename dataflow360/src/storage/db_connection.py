"""Connexion PostgreSQL et MongoDB (lit les variables d'environnement)."""

import os

import psycopg
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "dataflow_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "dataflow")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")


def get_pg_connection():
    """Crée et renvoie une connexion PostgreSQL."""
    return psycopg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "dataflow_raw")


def get_mongo_db():
    """Crée et renvoie la base MongoDB."""
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[MONGO_DB]


def get_mongo_client() -> MongoClient:
    """Crée et renvoie un client MongoDB."""
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


def test_mongo_connection() -> bool:
    """Test la connexion MongoDB."""
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        client.close()
        return True
    except PyMongoError as error:
        print(f"Erreur de connexion MongoDB : {error}")
        return False


if __name__ == "__main__":
    if test_mongo_connection():
        print("Connexion MongoDB réussie.")
    else:
        print("Échec de la connexion MongoDB.")
