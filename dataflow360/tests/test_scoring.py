import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

FAKE_ART = {
    "threshold": 0.7,
    "features": ["amount_xof", "hour_of_day", "geo_mismatch_count"],
    "pipeline": MagicMock(),
    "model_name": "fake_model",
}

with patch("joblib.load", return_value=FAKE_ART):
    from src.ml.fraud_detection import scoring


def base_commande(**overrides):
    cmd = {
        "order_id": "CMD-001",
        "country_code": "SN",
        "ip_country": "SN",
        "payment_source_country": "SN",
        "amount_xof": 50000,
        "hour_of_day": 14,
        "day_of_week": 2,
        "velocity_count_60s": 1,
        "payment_attempt_number": 1,
        "payment_method": "credit_card",
        "payment_status": "success",
    }
    cmd.update(overrides)
    return cmd


# ---- tests de base ----

def test_construire_features_aucune_anomalie_geo():
    f = scoring._construire_features(base_commande())
    assert f["geo_mismatch_count"] == 0


def test_construire_features_tout_different():
    cmd = base_commande(country_code="SN", ip_country="FR", payment_source_country="CI")
    f = scoring._construire_features(cmd)
    assert f["geo_mismatch_count"] == 3


def test_construire_features_sans_carte():
    cmd = base_commande(payment_source_country=None, ip_country="SN")
    f = scoring._construire_features(cmd)
    assert f["payment_source_country"] == "AUCUN"
    assert f["geo_card_client"] == 0
    assert f["geo_ip_card"] == 0


def test_niveau_alerte_forte():
    assert scoring._niveau(0.7, 0) == "ALERTE_FORTE"
    assert scoring._niveau(0.95, 0) == "ALERTE_FORTE"


def test_niveau_a_verifier_zone_grise():
    assert scoring._niveau(0.5, 2) == "A_VERIFIER"


def test_niveau_ok_zone_grise_sans_mismatch():
    assert scoring._niveau(0.5, 1) == "OK"


def test_niveau_ok_proba_basse():
    assert scoring._niveau(0.1, 3) == "OK"


# ---- tests supplémentaires ----

def test_construire_features_insensible_a_la_casse():
    """'sn' et 'SN' doivent être traités comme le même pays."""
    cmd = base_commande(country_code="sn", ip_country="SN")
    f = scoring._construire_features(cmd)
    assert f["geo_ip_client"] == 0


def test_niveau_pile_au_seuil_gris():
    """proba exactement à 0.30 avec 2 mismatchs -> A_VERIFIER (borne incluse)."""
    assert scoring._niveau(0.30, 2) == "A_VERIFIER"


def test_niveau_pile_au_seuil_alerte():
    """proba exactement au seuil du modèle -> ALERTE_FORTE (borne incluse)."""
    assert scoring._niveau(scoring.SEUIL, 0) == "ALERTE_FORTE"


def test_evaluer_commande_champs_manquants():
    """Une commande incomplète doit lever une ValueError explicite."""
    cmd = base_commande()
    del cmd["amount_xof"]
    with pytest.raises(ValueError, match="amount_xof"):
        scoring.evaluer_commande(cmd)


def test_evaluer_commande_structure_resultat(monkeypatch):
    """Vérifie que le dictionnaire renvoyé par evaluer_commande est complet et cohérent."""
    fake_pipeline = MagicMock()
    fake_pipeline.predict_proba.return_value = np.array([[0.1, 0.9]])  # proba de fraude = 0.9

    monkeypatch.setattr(scoring, "ART", {
        "threshold": 0.7,
        "features": ["amount_xof", "hour_of_day", "geo_mismatch_count"],
        "pipeline": fake_pipeline,
        "model_name": "fake_model",
    })
    monkeypatch.setattr(scoring, "SEUIL", 0.7)

    resultat = scoring.evaluer_commande(base_commande(order_id="CMD-XYZ"))

    assert resultat["order_id"] == "CMD-XYZ"
    assert resultat["niveau"] == "ALERTE_FORTE"
    assert resultat["alerte_vendeur"] is True
    assert resultat["probabilite"] == 0.9
    assert resultat["modele"] == "fake_model"
    assert "raison" in resultat


def test_evaluer_evenement_extrait_bien_la_date(monkeypatch):
    """evaluer_evenement doit extraire hour_of_day et day_of_week du timestamp ISO."""
    fake_pipeline = MagicMock()
    fake_pipeline.predict_proba.return_value = np.array([[0.95, 0.05]])  # proba de fraude = 0.05

    monkeypatch.setattr(scoring, "ART", {
        "threshold": 0.7,
        "features": ["amount_xof", "hour_of_day", "geo_mismatch_count"],
        "pipeline": fake_pipeline,
        "model_name": "fake_model",
    })
    monkeypatch.setattr(scoring, "SEUIL", 0.7)

    event = {
        "order_id": "CMD-EVT",
        "event_timestamp": "2026-10-08T14:30:00",
        "ip_country": "SN",
        "payment_source_country": "SN",
        "order_total_amount": 20000,
        "payment_attempt": 1,
        "payment_method": "mobile_money",
        "payment_status": "success",
    }

    resultat = scoring.evaluer_evenement(event, country_code="SN", velocity_count_60s=1)

    assert resultat["order_id"] == "CMD-EVT"
    assert resultat["niveau"] == "OK"