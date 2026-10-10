"""Extraction, vectorisation et insertion des textes RAG (étapes 68, 69, 70).

Source des textes : tables PostgreSQL `order_reviews` / `support_tickets` si elles existent,
sinon collections MongoDB du même nom (zone Landing).
Usage : python -m src.rag.indexer [--tenant UUID] [--max 5000]
"""

import argparse
import os

from src.rag.assistant import EMBED_MODEL, get_embedder, to_pgvector
from src.storage.db_connection import get_mongo_db, get_pg_connection
from src.storage.tenants import resolve_tenant_id

REVIEW_FIELDS = ("review_comment", "review_comment_message", "review_message")
TICKET_FIELDS = ("message", "ticket_message", "text", "description")


def _table_exists(conn, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
        return cur.fetchone()[0] is not None


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _from_mongo(collection: str, fields: tuple, tenant_ids: list) -> list[str]:
    docs = get_mongo_db()[collection].find({"tenant_id": {"$in": tenant_ids}})
    texts = []
    for doc in docs:
        value = next((doc[f] for f in fields if doc.get(f)), "")
        if _clean(value):
            texts.append(_clean(value))
    return texts


def fetch_texts_to_embed(conn, tenant_id: str) -> list[tuple[str, str]]:
    """Tuples (source_type, texte) pour les avis produits et les tickets support."""
    mongo_tenants = [tenant_id, os.getenv("MONGO_TENANT_ID", "tenant_demo")]
    out: list[tuple[str, str]] = []
    if _table_exists(conn, "order_reviews"):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 'review', review_comment FROM order_reviews WHERE tenant_id = %s",
                (tenant_id,),
            )
            out += [(s, _clean(t)) for s, t in cur.fetchall() if _clean(t)]
    else:
        out += [("review", t) for t in _from_mongo("order_reviews", REVIEW_FIELDS, mongo_tenants)]
    if _table_exists(conn, "support_tickets"):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 'support_ticket', message FROM support_tickets WHERE tenant_id = %s",
                (tenant_id,),
            )
            out += [(s, _clean(t)) for s, t in cur.fetchall() if _clean(t)]
    else:
        out += [
            ("support_ticket", t)
            for t in _from_mongo("support_tickets", TICKET_FIELDS, mongo_tenants)
        ]
    return out


def index_tenant(conn, tenant_id: str, max_docs: int = 5000, batch: int = 64) -> int:
    texts = fetch_texts_to_embed(conn, tenant_id)
    # dédoublonnage + plafond pour que l'indexation reste rapide sur un laptop
    seen, unique = set(), []
    for item in texts:
        if item[1] not in seen:
            seen.add(item[1])
            unique.append(item)
    unique = unique[:max_docs]
    if not unique:
        print("Aucun texte à indexer (order_reviews / support_tickets vides ?).")
        return 0

    model = get_embedder()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM rag_documents WHERE tenant_id = %s", (tenant_id,))  # idempotent
        for i in range(0, len(unique), batch):
            chunk = unique[i : i + batch]
            embeddings = model.encode([t for _, t in chunk], normalize_embeddings=True)
            assert len(embeddings[0]) == 384, "VECTOR(384) attendu"
            for (source_type, text), emb in zip(chunk, embeddings):
                cur.execute(
                    "INSERT INTO rag_documents (tenant_id, source_type, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (tenant_id, source_type, text, to_pgvector(emb)),
                )
            print(f"  {min(i + batch, len(unique))}/{len(unique)} textes vectorisés", flush=True)
    conn.commit()
    return len(unique)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tenant")
    p.add_argument("--max", type=int, default=int(os.getenv("RAG_MAX_DOCS", 5000)))
    a = p.parse_args()
    connection = get_pg_connection()
    tid = a.tenant or resolve_tenant_id(connection)
    print(f"Indexation RAG du tenant {tid} (modèle {EMBED_MODEL})")
    n = index_tenant(connection, tid, a.max)
    print(f"{n} documents insérés dans rag_documents.")
    connection.close()
