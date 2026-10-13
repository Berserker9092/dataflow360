import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.clean_olist import stock_status


def test_stock_status_rupture():
    assert stock_status(quantity=0, threshold=10) == "RUPTURE"


def test_stock_status_alerte():
    assert stock_status(quantity=5, threshold=10) == "ALERTE"


def test_stock_status_alerte_limite():
    assert stock_status(quantity=10, threshold=10) == "ALERTE"


def test_stock_status_ok():
    assert stock_status(quantity=50, threshold=10) == "OK"
