def stock_status(qty: int, threshold: int) -> str:
    """Détermine le statut du stock en fonction de la quantité et du seuil d'alerte."""
    if qty <= 0:
        return "RUPTURE"
    elif qty <= threshold:
        return "ALERTE"
    return "OK"
