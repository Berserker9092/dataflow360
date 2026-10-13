import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.clean_olist import clean_orders, clean_products


def test_clean_orders_supprime_doublons():
    df = pl.DataFrame({
        "order_id": ["1", "1", "2"],
        "customer_id": ["c1", "c1", "c2"],
        "order_status": ["delivered", "delivered", "shipped"],
        "order_purchase_timestamp": ["2026-01-01 10:00:00", "2026-01-01 10:00:00", "2026-01-02 11:00:00"],
        "order_total_amount": ["100", "100", "200"],
    })
    result = clean_orders(df)
    assert result.height == 2


def test_clean_orders_supprime_lignes_sans_id():
    df = pl.DataFrame({
        "order_id": ["1", None],
        "customer_id": ["c1", "c2"],
        "order_status": ["delivered", "shipped"],
        "order_purchase_timestamp": ["2026-01-01 10:00:00", "2026-01-02 11:00:00"],
        "order_total_amount": ["100", "200"],
    })
    result = clean_orders(df)
    assert result.height == 1


def test_clean_products_renomme_category():
    df = pl.DataFrame({
        "product_id": ["p1"],
        "category_name": ["electronique"],
        "product_cost": ["50"],
        "stock_quantity": ["10"],
        "stock_alert_threshold": ["5"],
    })
    result = clean_products(df)
    assert "category" in result.columns
    assert result["category"][0] == "electronique"


def test_clean_products_supprime_doublons():
    df = pl.DataFrame({
        "product_id": ["p1", "p1"],
        "category_name": ["electronique", "electronique"],
        "product_cost": ["50", "50"],
        "stock_quantity": ["10", "10"],
        "stock_alert_threshold": ["5", "5"],
    })
    result = clean_products(df)
    assert result.height == 1
