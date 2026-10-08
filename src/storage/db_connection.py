from pymongo import MongoClient
from pymongo.errors import PyMongoError


MONGO_URI = "mongodb://localhost:27017"
DATABASE_NAME = "dataflow360"


def get_mongo_client() -> MongoClient:
    """Create and return a MongoDB client."""
    return MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
    )


def test_mongo_connection() -> bool:
    """Test the connection to MongoDB."""
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
