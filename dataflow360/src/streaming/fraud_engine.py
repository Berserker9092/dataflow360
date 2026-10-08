"""Règle de fraude minimale par montant (ancienne version, conservée pour compatibilité).

Le moteur complet (vélocité, géographie, test de paiement, ML) est dans
src/ml/fraud_detection/scoring.py.
"""

SUSPICIOUS_AMOUNT_XOF = 500_000


def evaluate_order_risk(order_data: dict) -> dict:
    """Si amount > 500 000 XOF => BLOCK, sinon PASS."""
    amount = float(order_data.get("amount", 0))
    if amount > SUSPICIOUS_AMOUNT_XOF:
        return {"action": "BLOCK", "reason": "Montant anormalement élevé"}
    return {"action": "PASS", "reason": "Transaction normale"}
