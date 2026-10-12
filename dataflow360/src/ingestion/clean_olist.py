import polars as pl


def clean_orders(df: pl.DataFrame) -> pl.DataFrame:
    """
    Nettoie les données de commandes avant chargement PostgreSQL.
    """
    return (
        df.unique(subset=["order_id"])
        .drop_nulls(subset=["order_id", "customer_id"])
        .with_columns(
            pl.col("order_purchase_timestamp")
            .str.to_datetime(strict=False),
            pl.col("order_total_amount")
            .cast(pl.Int64),
        )
        .select([
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_total_amount",
        ])
    )


def stock_status(quantity: int, threshold: int) -> str:
    """
    Détermine le statut du stock à partir du seuil configuré.

    - 0 : RUPTURE
    - <= seuil : ALERTE
    - > seuil : OK
    """
    if quantity == 0:
        return "RUPTURE"

    if quantity <= threshold:
        return "ALERTE"

    return "OK"
def clean_products(df: pl.DataFrame) -> pl.DataFrame:
    """
    Nettoie les données produits avant chargement PostgreSQL.

    Règles :
    - supprimer les doublons sur product_id ;
    - supprimer les lignes sans product_id ;
    - convertir les colonnes numériques ;
    - renommer category_name en category.
    """
    return (
        df.unique(subset=["product_id"])
        .drop_nulls(subset=["product_id"])
        .with_columns(
            pl.col("product_cost").cast(pl.Int64),
            pl.col("stock_quantity").cast(pl.Int64),
            pl.col("stock_alert_threshold").cast(pl.Int64),
        )
        .rename({"category_name": "category"})
        .select([
            "product_id",
            "category",
            "product_cost",
            "stock_quantity",
            "stock_alert_threshold",
        ])
    )

def clean_products(df: pl.DataFrame) -> pl.DataFrame:
    """
    Nettoie les données produits avant chargement PostgreSQL.
    """
    return (
        df.unique(subset=["product_id"])
        .drop_nulls(subset=["product_id"])
        .with_columns(
            pl.col("product_cost").cast(pl.Int64),
            pl.col("stock_quantity").cast(pl.Int64),
            pl.col("stock_alert_threshold").cast(pl.Int64),
        )
        .rename({"category_name": "category"})
        .select([
            "product_id",
            "category",
            "product_cost",
            "stock_quantity",
            "stock_alert_threshold",
        ])
    )
