import csv
import datetime
from pathlib import Path

from src.storage.db_connection import get_mongo_client

# Chemin vers les données brutes
RAW_DATA_DIR = Path("data/raw")

# Configuration MongoDB
DATABASE_NAME = "dataflow360"

# Tenant utilisé pour le chargement historique
TENANT_ID = "tenant_demo"

# Nombre de documents insérés à chaque lot
BATCH_SIZE = 1000


def load_csv_to_mongo(csv_path: Path, database):
    """
    Charge un fichier CSV dans une collection MongoDB.

    Le chargement est idempotent pour le tenant de démonstration :
    les anciens documents de ce tenant sont supprimés avant rechargement.
    """
    collection_name = csv_path.stem
    collection = database[collection_name]

    print(f"\nChargement de {csv_path.name}...")
    print(f"Collection MongoDB : {collection_name}")

    # Idempotence : supprimer les anciennes données du tenant
    collection.delete_many({"tenant_id": TENANT_ID})

    batch = []
    total_inserted = 0

    with csv_path.open(
        mode="r",
        encoding="utf-8",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            row["tenant_id"] = TENANT_ID
            row["_source_file"] = csv_path.name
            row["_ingested_at"] = datetime.datetime.utcnow().isoformat()

            batch.append(row)

            if len(batch) >= BATCH_SIZE:
                collection.insert_many(batch)
                total_inserted += len(batch)
                batch = []

        # Insérer le dernier lot
        if batch:
            collection.insert_many(batch)
            total_inserted += len(batch)

    print(f"✓ {total_inserted} documents insérés")


def load_all_csv_to_mongo():
    """
    Charge tous les fichiers CSV présents dans data/raw/
    vers MongoDB.
    """
    client = get_mongo_client()
    database = client[DATABASE_NAME]

    try:
        csv_files = sorted(RAW_DATA_DIR.glob("*.csv"))

        if not csv_files:
            print("Aucun fichier CSV trouvé dans data/raw/")
            return

        print(f"{len(csv_files)} fichiers CSV trouvés.")

        for csv_path in csv_files:
            load_csv_to_mongo(csv_path, database)

        print("\n✓ Chargement terminé.")
        print(f"Base MongoDB : {DATABASE_NAME}")
        print(f"Tenant : {TENANT_ID}")

    finally:
        client.close()


if __name__ == "__main__":
    load_all_csv_to_mongo()
