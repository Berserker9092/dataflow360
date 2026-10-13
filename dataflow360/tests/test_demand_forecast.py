import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.demand_forecast.train import wape, rmse, poisson_dev, encode_categories


def test_wape_calcul_simple():
    y = np.array([10, 20, 0])
    p = np.array([10, 15, 5])
    # erreur absolue totale = 0 + 5 + 5 = 10, total vendu = 30 -> wape = 10/30
    assert wape(y, p) == pytest.approx(10 / 30)


def test_wape_prevision_parfaite():
    y = np.array([5, 10, 15])
    assert wape(y, y) == pytest.approx(0.0)


def test_rmse_calcul_simple():
    y = np.array([1, 2, 3])
    p = np.array([1, 2, 4])
    # une seule erreur de 1 sur 3 points -> rmse = sqrt(1/3)
    assert rmse(y, p) == pytest.approx((1 / 3) ** 0.5)


def test_poisson_dev_prevision_parfaite():
    y = np.array([1.0, 2.0, 3.0])
    assert poisson_dev(y, y) == pytest.approx(0.0, abs=1e-6)


def test_poisson_dev_vente_nulle():
    """Quand la vente reelle est 0, le terme logarithmique est ignore (pas de log(0))."""
    y = np.array([0.0])
    p = np.array([2.0])
    assert poisson_dev(y, p) == pytest.approx(4.0)


def test_encode_categories_mode_entrainement():
    """Sans 'levels', on apprend les categories dans l'ordre de premiere apparition."""
    cat = ["A", "B", "A", "C"]
    codes, levels = encode_categories(cat)
    assert codes.tolist() == [0, 1, 0, 2]
    assert levels == ["A", "B", "C"]


def test_encode_categories_mode_prediction_categorie_connue():
    codes, levels = encode_categories(["B", "A"], levels=["A", "B", "C"])
    assert codes.tolist() == [1, 0]


def test_encode_categories_mode_prediction_categorie_inconnue():
    """Une categorie jamais vue a l'entrainement doit donner le code -1."""
    codes, levels = encode_categories(["D"], levels=["A", "B", "C"])
    assert codes.tolist() == [-1]
