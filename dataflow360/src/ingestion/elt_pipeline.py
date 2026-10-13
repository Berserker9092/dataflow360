"""Pipeline ETL : MongoDB → PostgreSQL.

Extrait les collections MongoDB et les charge dans PostgreSQL.
Usage : python -m src.ingestion.elt_pipeline
"""

import os

import polars as pl

from src.storage.db_connection import get_mongo_client, get_pg_connection

DATABASE_NAME = "dataflow360"

TENANT_NAME = os.getenv("TENANT_NAME", "Boutique démo")


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------
def get_mongo_db():
    client = get_mongo_client()
    return client[DATABASE_NAME]


def extract(collection_name: str) -> pl.DataFrame:
    db = get_mongo_db()
    docs = list(db[collection_name].find({}, {"_id": 0}))
    if not docs:
        return pl.DataFrame()
    return pl.DataFrame(docs)


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------
def get_tenant_uuid():
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM tenants WHERE name = %s",
                (TENANT_NAME,),
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit(f"Tenant PostgreSQL introuvable : {TENANT_NAME}")
            return str(row[0])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
def load_customers(df: pl.DataFrame, tenant_uuid: str) -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM customers WHERE tenant_id = %s", (tenant_uuid,))

            rows = []
            for r in df.iter_rows(named=True):
                rows.append((
                    tenant_uuid,
                    r.get("customer_id"),
                    r.get("customer_city"),
                    r.get("country_code"),
                    r.get("full_name"),
                    r.get("email"),
                    r.get("phone"),
                ))

            cur.executemany(
                """
                INSERT INTO customers
                (tenant_id, customer_id, city, country, full_name, email, phone)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, customer_id) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
def load_products(df: pl.DataFrame, tenant_uuid: str) -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE tenant_id = %s", (tenant_uuid,))

            rows = []
            for r in df.iter_rows(named=True):
                rows.append((
                    tenant_uuid,
                    r.get("product_id"),
                    r.get("product_name"),
                    r.get("category_name"),
                    r.get("product_cost"),
                    r.get("stock_quantity"),
                    r.get("stock_alert_threshold"),
                ))

            cur.executemany(
                """
                INSERT INTO products
                (tenant_id, product_id, product_name, category,
                 product_cost, stock_quantity, stock_alert_threshold)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, product_id) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def load_orders(df: pl.DataFrame, tenant_uuid: str) -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM orders WHERE tenant_id = %s", (tenant_uuid,))

            rows = []
            for r in df.iter_rows(named=True):
                rows.append((
                    tenant_uuid,
                    r.get("order_id"),
                    r.get("customer_id"),
                    r.get("order_status"),
                    r.get("order_purchase_timestamp"),
                    r.get("order_total_amount"),
                ))

            cur.executemany(
                """
                INSERT INTO orders
                (tenant_id, order_id, customer_id, order_status,
                 order_purchase_timestamp, order_total_amount)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, order_id) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Order items
# ---------------------------------------------------------------------------
def load_order_items(df: pl.DataFrame, tenant_uuid: str) -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM order_items WHERE tenant_id = %s", (tenant_uuid,))

            rows = []
            for r in df.iter_rows(named=True):
                rows.append((
                    tenant_uuid,
                    r.get("order_id"),
                    r.get("order_item_id"),
                    r.get("product_id"),
                    r.get("quantity", 1) or 1,
                    r.get("item_total"),
                ))

            cur.executemany(
                """
                INSERT INTO order_items
                (tenant_id, order_id, order_item_id, product_id, quantity, item_total)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, order_id, order_item_id) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fraud ground truth
# ---------------------------------------------------------------------------
def load_fraud_ground_truth(df: pl.DataFrame, tenant_uuid: str) -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fraud_ground_truth WHERE tenant_id = %s", (tenant_uuid,))

            rows = []
            for r in df.iter_rows(named=True):
                rows.append((
                    tenant_uuid,
                    r.get("order_id"),
                    bool(r.get("is_fraudulent", False)),
                    r.get("fraud_type"),
                ))

            cur.executemany(
                """
                INSERT INTO fraud_ground_truth
                (tenant_id, order_id, is_fraudulent, fraud_type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, order_id) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =============================================================================
# Pipeline
# =============================================================================
def main():
    print("=== Pipeline ETL : MongoDB → PostgreSQL ===")
    print(f"Tenant : {TENANT_NAME}")

    tenant_uuid = get_tenant_uuid()
    print(f"Tenant UUID : {tenant_uuid}")
    print()

    # ÉTAPE 1 : Vider les tables dans le BON ORDRE (dépendances FK)
    print("Nettoyage des tables (ordre FK)...")
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            # Ordre inverse des dépendances
            cur.execute("DELETE FROM order_items WHERE tenant_id = %s", (tenant_uuid,))
            cur.execute("DELETE FROM fraud_ground_truth WHERE tenant_id = %s", (tenant_uuid,))
            cur.execute("DELETE FROM orders WHERE tenant_id = %s", (tenant_uuid,))
            cur.execute("DELETE FROM products WHERE tenant_id = %s", (tenant_uuid,))
            cur.execute("DELETE FROM customers WHERE tenant_id = %s", (tenant_uuid,))
        conn.commit()
        print("  ✅ Tables vidées")
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Erreur nettoyage : {e}")
    finally:
        conn.close()
    print()

    # ÉTAPE 2 : Charger les données dans le bon ordre
    steps = [
        ("customers", load_customers),
        ("products", load_products),
        ("orders", load_orders),
        ("order_items", load_order_items),
        ("fraud_ground_truth", load_fraud_ground_truth),
    ]

    for name, loader in steps:
        try:
            df = extract(name)
            print(f"  {name}: {len(df)} lus")
            if len(df) == 0:
                print(f"    ⚠️  0 documents, ignoré")
                continue
            n = loader(df, tenant_uuid)
            print(f"    ✅ {n} chargés")
        except Exception as e:
            print(f"    ❌ ERREUR : {e}")

    print()
    print("=== ETL Batch terminé ===")

if __name__ == "__main__":
    main()
