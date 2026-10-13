"""
Module ML de détection de fraude.

Fournit :
- risk_level(score)                    → niveau de risque (ELEVE / MOYEN / FAIBLE)
- evaluer_commande / evaluer_evenement  → évaluation directe
- score_event(event, conn, r)          → appelé par le consumer via Redis
"""

import json
import time
from datetime import datetime
from pathlib import Path

import joblib
import polars as pl

# ---------------------------------------------------------------------------
# Chargement du modèle (avec fallback si absent)
# ---------------------------------------------------------------------------
try:
    ART = joblib.load(Path(__file__).parent / "models" / "fraud_model.pkl")
    SEUIL = ART["threshold"]
    print("✅ Modèle ML de fraude chargé", flush=True)
except FileNotFoundError:
    ART = None
    SEUIL = 0.5
    print("⚠️  Pas de modèle ML, utilisation des règles seules", flush=True)

SEUIL_GRIS = 0.30

CHAMPS_REQUIS = [
    "order_id", "country_code", "ip_country", "payment_source_country",
    "amount_xof", "hour_of_day", "day_of_week", "velocity_count_60s",
    "payment_attempt_number", "payment_method", "payment_status",
]


# ---------------------------------------------------------------------------
# Niveau de risque (utilisé par l'API)
# ---------------------------------------------------------------------------
def risk_level(score: int) -> str:
    """Convertit un score 0-100 en niveau de risque."""
    if score >= 70:
        return "ELEVE"
    if score >= 30:
        return "MOYEN"
    return "FAIBLE"


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
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
        return "ALERTE_FORTE"
    if proba >= SEUIL_GRIS and geo_count >= 2:
        return "A_VERIFIER"
    return "OK"


# ---------------------------------------------------------------------------
# Évaluation d'une commande
# ---------------------------------------------------------------------------
def evaluer_commande(cmd: dict) -> dict:
    """Reçoit une commande brute, renvoie la décision du modèle."""
    manquants = [c for c in CHAMPS_REQUIS if c not in cmd]
    if manquants:
        raise ValueError(f"Champs manquants : {manquants}")

    f = _construire_features(cmd)

    # --- Mode RÈGLES SEULES (pas de modèle ML) ---
    if ART is None:
        geo_count = f["geo_mismatch_count"]
        if geo_count >= 2:
            niveau, proba = "ALERTE_FORTE", 0.9
        elif geo_count >= 1:
            niveau, proba = "A_VERIFIER", 0.5
        else:
            niveau, proba = "OK", 0.1
        return {
            "order_id": cmd["order_id"],
            "niveau": niveau,
            "alerte_vendeur": niveau != "OK",
            "probabilite": proba,
            "geo_mismatch_count": geo_count,
            "raison": f"Règles seules : {geo_count} incohérence(s) géo",
            "modele": "regles_seules",
        }

    # --- Mode MODÈLE ML ---
    X = pl.DataFrame([f]).select(ART["features"])
    proba = float(ART["pipeline"].predict_proba(X)[0, 1])
    niveau = _niveau(proba, f["geo_mismatch_count"])
    raison = (
        f"IP en {f['ip_country']}, client en {str(cmd['country_code']).upper()}, "
        f"carte {f['payment_source_country']}, montant {f['amount_xof']} XOF"
    )
    return {
        "order_id": cmd["order_id"],
        "niveau": niveau,
        "alerte_vendeur": niveau != "OK",
        "probabilite": round(proba, 3),
        "geo_mismatch_count": f["geo_mismatch_count"],
        "raison": raison,
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
        "day_of_week": ts.weekday(),
        "velocity_count_60s": velocity_count_60s,
        "payment_attempt_number": event["payment_attempt"],
        "payment_method": event["payment_method"],
        "payment_status": event["payment_status"],
    }
    return evaluer_commande(cmd)


# ---------------------------------------------------------------------------
# Intégration consumer (Redis)
# ---------------------------------------------------------------------------
def score_event(event: dict, conn, r) -> dict:
    """Appelée par le consumer : score + écrit alertes dans Redis."""
    tenant_id = event.get("tenant_id", "00000000-0000-0000-0000-000000000001")
    customer_id = event.get("customer_id", "unknown")
    order_id = event.get("order_id", "unknown")

    # Pays du client
    country_code = "SN"
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT country FROM customers WHERE tenant_id = %s AND customer_id = %s",
                (tenant_id, customer_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                country_code = row[0]
    except Exception:
        pass

    # Vélocité
    velocity_count = 1
    try:
        vkey = f"velocity:{tenant_id}:{customer_id}"
        now_ts = time.time()
        r.zadd(vkey, {order_id: now_ts})
        r.expire(vkey, 60)
        velocity_count = r.zcard(vkey) or 1
    except Exception:
        pass

    # Appel modèle
    result = evaluer_evenement(event, country_code, velocity_count)

    # Score numérique
    proba = result.get("probabilite", 0.1)
    score = int(round(proba * 100))
    score = max(0, min(100, score))

    risk = risk_level(score)

    # Stats
    stats_key = f"fraud_stats:{tenant_id}"
    r.hincrby(stats_key, "scored", 1)

    # Alerte
    if result.get("alerte_vendeur") or score >= 30:
        r.hincrby(stats_key, "flagged", 1)
        alert_key = f"fraud_alerts:{tenant_id}"
        r.hset(
            alert_key,
            order_id,
            json.dumps({
                "score": score,
                "risk": risk,
                "reasons": [result.get("raison", "Règles seules")],
                "amount": event.get("order_total_amount", 0),
                "customer_id": customer_id,
                "ts": time.time(),
            }),
        )
        r.expire(alert_key, 86400)

    return {
        "score": score,
        "risk": risk,
        "reasons": [result.get("raison", "Règles seules")],
        "niveau": result.get("niveau", "OK"),
    }


# ---------------------------------------------------------------------------
# Test manuel
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    exemple = dict(
        order_id="CMD-002",
        country_code="CI",
        ip_country="BF",
        payment_source_country="SN",
        amount_xof=300000,
        hour_of_day=2,
        day_of_week=5,
        velocity_count_60s=2,
        payment_attempt_number=2,
        payment_method="credit_card",
        payment_status="failed",
    )
    print(evaluer_commande(exemple))
