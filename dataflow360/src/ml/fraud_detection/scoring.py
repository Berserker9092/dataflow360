"""
Module ML de détection de fraude (partie ML/IA).

Le backend importe ce fichier et appelle UNE seule fonction :

    from fraud_service import evaluer_commande
    resultat = evaluer_commande(commande)
"""
import joblib
import polars as pl
from datetime import datetime
from pathlib import Path

ART = joblib.load(Path(__file__).parent / "models" / "fraud_model.pkl")
SEUIL = ART["threshold"]       # seuil du modèle, choisi sur la validation
SEUIL_GRIS = 0.30              # zone grise (à valider sur les données de validation)

CHAMPS_REQUIS = [
    "order_id", "country_code", "ip_country", "payment_source_country",
    "amount_xof", "hour_of_day", "day_of_week", "velocity_count_60s",
    "payment_attempt_number", "payment_method", "payment_status",
]


def _construire_features(cmd: dict) -> dict:
    ip_c = str(cmd["ip_country"]).strip().upper()
    client_c = str(cmd["country_code"]).strip().upper()
    card_c = str(cmd.get("payment_source_country") or "AUCUN").strip().upper()

    geo_ip_client = int(ip_c != client_c)
    geo_card_client = 0 if card_c == "AUCUN" else int(card_c != client_c)
    geo_ip_card = 0 if card_c == "AUCUN" else int(ip_c != card_c)

    return {
        "amount_xof": cmd["amount_xof"],
        "hour_of_day": cmd["hour_of_day"],
        "day_of_week": cmd["day_of_week"],
        "velocity_count_60s": cmd["velocity_count_60s"],
        "geo_ip_client": geo_ip_client,
        "geo_card_client": geo_card_client,
        "geo_ip_card": geo_ip_card,
        "geo_mismatch_count": geo_ip_client + geo_card_client + geo_ip_card,
        "payment_attempt_number": cmd["payment_attempt_number"],
        "payment_method": cmd["payment_method"],
        "ip_country": ip_c,
        "payment_source_country": card_c,
        "payment_status": cmd["payment_status"],
    }


def _niveau(proba: float, geo_count: int) -> str:
    if proba >= SEUIL:
        return "ALERTE_FORTE"        # à afficher en priorité au vendeur
    if proba >= SEUIL_GRIS and geo_count >= 2:
        return "A_VERIFIER"          # zone grise
    return "OK"                      # pas d'alerte


def evaluer_commande(cmd: dict) -> dict:
    """Reçoit une commande brute, renvoie la décision du modèle."""
    manquants = [c for c in CHAMPS_REQUIS if c not in cmd]
    if manquants:
        raise ValueError(f"Champs manquants : {manquants}")

    f = _construire_features(cmd)
    X = pl.DataFrame([f]).select(ART["features"])
    proba = float(ART["pipeline"].predict_proba(X)[0, 1])
    niveau = _niveau(proba, f["geo_mismatch_count"])

    raison = (f"IP en {f['ip_country']}, client en {str(cmd['country_code']).upper()}, "
              f"carte {f['payment_source_country']}, montant {f['amount_xof']} XOF")

    return {
        "order_id": cmd["order_id"],
        "niveau": niveau,                        # OK / A_VERIFIER / ALERTE_FORTE
        "alerte_vendeur": niveau != "OK",        # True -> le backend crée l'alerte
        "probabilite": round(proba, 3),          # score de risque (pas un vrai pourcentage)
        "geo_mismatch_count": f["geo_mismatch_count"],
        "raison": raison,                        # texte à afficher au vendeur
        "modele": ART["model_name"],
    }

def evaluer_evenement(event: dict, country_code: str, velocity_count_60s: int) -> dict:
    """event = CheckoutEvent en dict ; country_code et vélocité sont fournis par le backend."""
    ts = datetime.fromisoformat(event["event_timestamp"])
    cmd = {
        "order_id": event["order_id"],
        "country_code": country_code,
        "ip_country": event["ip_country"],
        "payment_source_country": event.get("payment_source_country"),
        "amount_xof": event["order_total_amount"],
        "hour_of_day": ts.hour,
        "day_of_week": ts.weekday(),          # lundi = 0, comme à l'entraînement
        "velocity_count_60s": velocity_count_60s,
        "payment_attempt_number": event["payment_attempt"],
        "payment_method": event["payment_method"],
        "payment_status": event["payment_status"],
    }
    return evaluer_commande(cmd)


if __name__ == "__main__":
    exemple = dict(
        order_id="CMD-002", country_code="CI", ip_country="BF", payment_source_country="SN",
        amount_xof=300000, hour_of_day=2, day_of_week=5, velocity_count_60s=2,
        payment_attempt_number=2, payment_method="credit_card", payment_status="failed",
    )
    print(evaluer_commande(exemple));