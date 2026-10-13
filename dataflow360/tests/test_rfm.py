import sys
from pathlib import Path
from datetime import datetime

import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.batch.rfm_segmentation import calculate_rfm, score_rfm, segment_customer


def make_orders_df():
    return pl.DataFrame({
        "customer_id": ["c1", "c2", "c3"],
        "order_id": ["o1", "o2", "o3"],
        "order_purchase_timestamp": [
            datetime(2026, 1, 1),
            datetime(2026, 1, 10),
            datetime(2026, 1, 15),
        ],
        "order_total_amount": [100, 200, 300],
    })


def test_calculate_rfm_colonnes():
    result = calculate_rfm(make_orders_df())
    assert set(result.columns) == {"customer_id", "recency", "frequency", "monetary"}


def test_calculate_rfm_recence_la_plus_recente_est_zero():
    """Le client avec la date la plus récente doit avoir une récence de 0."""
    result = calculate_rfm(make_orders_df())
    most_recent = result.filter(pl.col("customer_id") == "c3")
    assert most_recent["recency"][0] == 0


def test_score_rfm_cinq_clients():
    df = pl.DataFrame({
        "customer_id": ["c1", "c2", "c3", "c4", "c5"],
        "recency": [5, 4, 3, 2, 1],
        "frequency": [1, 2, 3, 6, 10],
        "monetary": [100, 200, 300, 400, 500],
    })
    result = score_rfm(df).sort("customer_id")

    assert result["r_score"].to_list() == [1, 2, 3, 4, 5]
    assert result["f_score"].to_list() == [1, 2, 3, 5, 5]
    assert result["m_score"].to_list() == [1, 2, 3, 4, 5]
    assert result["rfm_score"].to_list() == [3, 6, 9, 13, 15]


def test_segment_champions():
    assert segment_customer({"r_score": 5, "f_score": 5, "m_score": 5}) == "Champions"


def test_segment_clients_fideles():
    assert segment_customer({"r_score": 3, "f_score": 4, "m_score": 1}) == "Clients fidèles"


def test_segment_a_risque():
    assert segment_customer({"r_score": 1, "f_score": 3, "m_score": 1}) == "À risque"


def test_segment_clients_perdus():
    """Cas limite : scores bas partout, sans déclencher 'À risque'."""
    assert segment_customer({"r_score": 1, "f_score": 1, "m_score": 1}) == "Clients perdus/faibles"


def test_segment_occasionnel_par_defaut():
    assert segment_customer({"r_score": 3, "f_score": 3, "m_score": 3}) == "Clients occasionnels"
