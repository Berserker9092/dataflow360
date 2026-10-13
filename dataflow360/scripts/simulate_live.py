"""
Simulateur de commandes temps réel pour DataFlow360.

Envoie des commandes toutes les N secondes via le webhook.
- 80% de commandes normales
- 20% de commandes suspectes (géo mismatch + payment failed)

Usage : python -m scripts.simulate_live
"""

import os
import random
import time
from datetime import datetime, timezone

import httpx

API_URL = os.getenv("API_URL", "http://api:8000")
API_KEY = os.getenv("DEMO_TENANT_KEY", "demo-key-change-me-123")
INTERVAL = float(os.getenv("SIM_INTERVAL", "3"))
SUSPECT_RATIO = float(os.getenv("SIM_SUSPECT_RATIO", "0.2"))

FIRST_NAMES = ["Aminata", "Awa", "Fatou", "Ibrahima", "Moussa", "Ousmane", "Cheikh"]
LAST_NAMES = ["Diallo", "Traoré", "Ndiaye", "Fall", "Sow", "Ba", "Diop"]


def random_event(i: int) -> dict:
    """Génère un événement de checkout aléatoire."""
    order_id = f"live-{int(time.time())}-{i}"
    is_suspect = random.random() < SUSPECT_RATIO

    if is_suspect:
        customer_id = f"suspect-{random.randint(1, 50)}"
        return {
            "event_id": f"evt-{order_id}",
            "event_type": "order_created",
            "order_id": order_id,
            "customer_id": customer_id,
            "order_total_amount": random.randint(3_000_000, 10_000_000),
            "currency": "XOF",
            "client_ip": "1.2.3.4",
            "ip_country": "RU",
            "payment_method": "crypto",
            "payment_source_country": "KP",
            "payment_status": "failed",
            "payment_attempt": random.randint(3, 8),
            "event_timestamp": datetime.now(timezone.utc).isoformat(),
        }
    else:
        customer_id = f"cust-{random.randint(1, 50)}"
        return {
            "event_id": f"evt-{order_id}",
            "event_type": "order_created",
            "order_id": order_id,
            "customer_id": customer_id,
            "order_total_amount": random.randint(10_000, 200_000),
            "currency": "XOF",
            "client_ip": f"41.82.0.{i % 255}",
            "ip_country": "SN",
            "payment_method": random.choice(["card", "cash"]),
            "payment_source_country": "SN",
            "payment_status": "approved",
            "payment_attempt": 1,
            "event_timestamp": datetime.now(timezone.utc).isoformat(),
        }


def main():
    print(f"🚀 Simulateur temps réel démarré")
    print(f"   API      : {API_URL}")
    print(f"   Interval : {INTERVAL}s")
    print(f"   Suspects : {int(SUSPECT_RATIO * 100)}%")
    print()

    i = 0
    with httpx.Client(timeout=10) as client:
        while True:
            i += 1
            event = random_event(i)
            is_suspect = event["customer_id"].startswith("suspect-")
            icon = "🚨" if is_suspect else "✅"

            try:
                r = client.post(
                    f"{API_URL}/webhook/order-created",
                    json=event,
                    headers={"X-Tenant-API-Key": API_KEY},
                )
                if r.status_code == 200:
                    print(f"{icon} {event['order_id']}")
                else:
                    print(f"❌ {event['order_id']} → HTTP {r.status_code}")
            except Exception as e:
                print(f"❌ {event['order_id']} → {e}")

            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
