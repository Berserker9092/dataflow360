import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.load_raw_mongo import load_csv_to_mongo


class FakeCollection:
    """Remplace une vraie collection MongoDB : on enregistre juste ce qu'on y insère."""
    def __init__(self):
        self.inserted = []

    def insert_many(self, documents):
        self.inserted.extend(documents)


class FakeDatabase:
    """Remplace une vraie base MongoDB : renvoie une FakeCollection par nom."""
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


def test_load_csv_to_mongo_insere_toutes_les_lignes(tmp_path):
    csv_path = tmp_path / "clients.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "nom"])
        writer.writeheader()
        writer.writerow({"id": "1", "nom": "Awa"})
        writer.writerow({"id": "2", "nom": "Moussa"})

    database = FakeDatabase()
    load_csv_to_mongo(csv_path, database)

    collection = database["clients"]
    assert len(collection.inserted) == 2
    assert collection.inserted[0] == {"id": "1", "nom": "Awa"}


def test_load_csv_to_mongo_nom_collection_sans_extension(tmp_path):
    csv_path = tmp_path / "produits.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id"])
        writer.writeheader()
        writer.writerow({"id": "1"})

    database = FakeDatabase()
    load_csv_to_mongo(csv_path, database)

    assert "produits" in database.collections


def test_load_csv_to_mongo_fichier_vide(tmp_path):
    """Cas limite : un CSV avec juste l'en-tête, aucune ligne de données."""
    csv_path = tmp_path / "vide.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id"])
        writer.writeheader()

    database = FakeDatabase()
    load_csv_to_mongo(csv_path, database)

    collection = database["vide"]
    assert collection.inserted == []