import polars as pl

from src.storage.db_connection import get_mongo_client, get_pg_connection

DATABASE_NAME = "dataflow360"
TENANT_NAME = "tenant_demo"


def get_mongo_db():
    client = get_mongo_client()
    return client[DATABASE_NAME]


def extract(collection_name: str) -> pl.DataFrame:
    """
    Extrait une collection MongoDB dans un DataFrame Polars.
    """
    db = get_mongo_db()

    docs = list(
        db[collection_name].find(
            {},
            {"_id": 0}
        )
    )

    return pl.DataFrame(docs)


def get_tenant_uuid():
    """
    Récupère l'UUID du tenant dans PostgreSQL.
    """
    conn = get_pg_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM tenants WHERE name = %s",
                (TENANT_NAME,)
            )
            row = cur.fetchone()

            if row is None:
                raise ValueError(
                    f"Tenant PostgreSQL introuvable : {TENANT_NAME}"
                )

            return row[0]
    finally:
        conn.close()


def load_customers(df: pl.DataFrame):
    """
    Charge les clients nettoyés dans PostgreSQL.
    """
    tenant_uuid = get_tenant_uuid()
    conn = get_pg_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM customers WHERE tenant_id = %s",
                (tenant_uuid,)
            )

            rows = [
                (
                    tenant_uuid,
                    row["customer_id"],
                    row.get("city"),
                    row.get("country"),
                )
                for row in df.iter_rows(named=True)
            ]

            cur.executemany(
                """
                INSERT INTO customers (
                    tenant_id,
                    customer_id,
                    city,
                    country
                )
                VALUES (%s, %s, %s, %s)
                """,
                rows,
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def load_products(df: pl.DataFrame):
    """
    Charge les produits nettoyés dans PostgreSQL.
    """
    tenant_uuid = get_tenant_uuid()
    conn = get_pg_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM products WHERE tenant_id = %s",
                (tenant_uuid,)
            )

            rows = [
                (
                    tenant_uuid,
                    row["product_id"],
                    row["category"],
                    row["product_cost"],
                    row["stock_quantity"],
                    row["stock_alert_threshold"],
                )
                for row in df.iter_rows(named=True)
            ]

            cur.executemany(
                """
                INSERT INTO products (
                    tenant_id,
                    product_id,
                    category,
                    product_cost,
                    stock_quantity,
                    stock_alert_threshold
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def load_orders(df: pl.DataFrame):
    tenant_uuid = get_tenant_uuid()
    conn = get_pg_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM orders WHERE tenant_id = %s",
                (tenant_uuid,)
            )

            rows = [
                (
                    tenant_uuid,
                    row["order_id"],
                    row["customer_id"],
                    row["order_status"],
                    row["order_purchase_timestamp"],
                    row["order_total_amount"],
                )
                for row in df.iter_rows(named=True)
            ]

            cur.executemany(
                """
                INSERT INTO orders (
                    tenant_id,
                    order_id,
                    customer_id,
                    order_status,
                    order_purchase_timestamp,
                    order_total_amount
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
