import polars as pl

from src.storage.db_connection import get_pg_connection


def extract_delivered_orders() -> pl.DataFrame:
    """Extract delivered orders from PostgreSQL."""
    conn = get_pg_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    customer_id,
                    order_id,
                    order_purchase_timestamp,
                    order_total_amount
                FROM orders
                WHERE order_status = 'delivered'
                """
            )

            rows = cur.fetchall()

        return pl.DataFrame(
            rows,
            schema=[
                "customer_id",
                "order_id",
                "order_purchase_timestamp",
                "order_total_amount",
            ],
            orient="row",
        )

    finally:
        conn.close()


def calculate_rfm(df: pl.DataFrame) -> pl.DataFrame:
    """Calculate Recency, Frequency and Monetary for each customer."""
    reference_date = df["order_purchase_timestamp"].max()

    return (
        df.group_by("customer_id")
        .agg(
            pl.col("order_purchase_timestamp").max().alias("last_purchase"),
            pl.col("order_id").n_unique().alias("frequency"),
            pl.col("order_total_amount").sum().alias("monetary"),
        )
        .with_columns(
            (
                (pl.lit(reference_date) - pl.col("last_purchase"))
                .dt.total_days()
            ).alias("recency")
        )
        .select([
            "customer_id",
            "recency",
            "frequency",
            "monetary",
        ])
    )


def score_rfm(df: pl.DataFrame) -> pl.DataFrame:
    """Assign RFM scores from 1 to 5 using percentile ranks."""
    return (
        df.with_columns(
            (
                6
                - (
                    pl.col("recency")
                    .rank(method="average") / pl.len()
                    * 5
                ).ceil()
            )
            .cast(pl.Int64)
            .alias("r_score"),

            pl.when(pl.col("frequency") >= 5)
            .then(5)
            .otherwise(pl.col("frequency"))
            .cast(pl.Int64)
            .alias("f_score"),

            (
                (
                    pl.col("monetary")
                    .rank(method="average") / pl.len()
                    * 5
                ).ceil()
            )
            .cast(pl.Int64)
            .alias("m_score"),
        )
        .with_columns(
            (
                pl.col("r_score")
                + pl.col("f_score")
                + pl.col("m_score")
            ).alias("rfm_score")
        )
    )


def segment_customer(row: dict) -> str:
    """Assign a business segment to a customer from RFM scores."""
    r = row["r_score"]
    f = row["f_score"]
    m = row["m_score"]

    if r >= 4 and f >= 4 and m >= 4:
        return "Champions"

    if f >= 4 and r >= 3:
        return "Clients fidèles"

    if m >= 4:
        return "Gros dépensiers"

    if r <= 2 and (f >= 3 or m >= 4):
        return "À risque"

    if r >= 4:
        return "Prometteurs"

    if r <= 2 and f <= 2 and m <= 2:
        return "Clients perdus/faibles"

    return "Clients occasionnels"
