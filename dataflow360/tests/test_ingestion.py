import polars as pl
import pytest
from src.ingestion.clean_olist import clean_orders, clean_products, stock_status


def test_clean_orders_deduplication_and_nulls():
    # Données fictives simulant des commandes brutes avec doublons et valeurs nulles
    data = {
        "order_id": ["O1", "O2", "O1", None],
        "customer_id": ["C1", "C2", "C1", "C3"],
        "order_status": ["delivered", "shipped", "delivered", "processing"],
        "order_purchase_timestamp": ["2026-01-01 10:00:00", "2026-01-02 11:00:00", "2026-01-01 10:00:00", "2026-01-03 12:00:00"],
        "order_total_amount": ["100.50", "200.00", "100.50", "50.25"],
    }
    df = pl.DataFrame(data)
    
    cleaned_df = clean_orders(df)
    
    # Vérifications : plus de doublons sur order_id, pas de nulls sur order_id/customer_id, et 2 lignes restantes
    assert cleaned_df.height == 2
    assert cleaned_df["order_id"].to_list() == ["O1", "O2"]
    # Vérifie le cast en Int64 sur order_total_amount selon la logique d'Ousmane
    assert cleaned_df["order_total_amount"].dtype == pl.Int64


def test_stock_status_logic():
    # Test des seuils de stock définis par Ousmane
    assert stock_status(0, 5) == "RUPTURE"
    assert stock_status(3, 5) == "ALERTE"
    assert stock_status(5, 5) == "ALERTE"
    assert stock_status(10, 5) == "OK"


def test_clean_products():
    data = {
        "product_id": ["P1", "P2", "P1"],
        "category_name": ["Electronics", "Books", "Electronics"],
        "product_cost": ["50", "20", "50"],
        "stock_quantity": ["10", "0", "10"],
        "stock_alert_threshold": ["5", "5", "5"],
    }
    df = pl.DataFrame(data)
    
    cleaned_df = clean_products(df)
    
    # Vérifications sur le renommage de catégorie et la suppression des doublons
    assert cleaned_df.height == 2
    assert "category" in cleaned_df.columns
    assert "category_name" not in cleaned_df.columns
    assert cleaned_df["product_cost"].dtype == pl.Int64