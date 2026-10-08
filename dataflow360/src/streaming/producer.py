"""Simulateur de trafic client (étape 48) : rejoue checkout_events.csv dans le temps.

Par défaut chaque commande reçoit un identifiant neuf (suffixe -L<run>) : sans cela, les
commandes existent déjà dans le warehouse et le chiffre d'affaires ne bougerait pas. L'horodatage
d'origine est conservé (pas de trou de plusieurs mois dans l'historique des prévisions) ;
--now le remplace par l'heure courante.
"""

import argparse
import csv
import os
import random
import time
from collections import defaultdict
from datetime import datetime, timezone

import httpx

from src import config

API_URL = os.getenv("API_URL", config.API_URL)


def load_items_by_order(path: str = "data/raw/order_items.csv") -> dict:
    items = defaultdict(list)
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            items[row["order_id"]].append(
                {
                    "product_id": row["product_id"],
                    "quantity": int(float(row.get("quantity") or 1)),
                    "item_total": int(float(row["item_total"])),
                }
            )
    return items


def normalize(row: dict) -> dict:
    """Types du contrat API (étape 20) : entiers sans décimales, vide -> None."""
    row = dict(row)
    for field in ("order_total_amount", "payment_attempt"):
        row[field] = int(float(row[field]))
    row["payment_source_country"] = row.get("payment_source_country") or None
    return row


def simulate_live_traffic(
    csv_path: str = "data/raw/checkout_events.csv",
    min_delay: float = 2.0,
    max_delay: float = 8.0,
    limit: int | None = None,
    fresh_ids: bool = True,
    stamp_now: bool = False,
    api_key: str | None = None,
) -> None:
    api_key = api_key or os.getenv("DEMO_TENANT_KEY", "")
    if not api_key:
        raise SystemExit("DEMO_TENANT_KEY manquante (.env.local ou variable d'environnement).")
    items_by_order = load_items_by_order()
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: r["event_timestamp"])
    if limit:
        rows = rows[:limit]
    run_id = datetime.now(timezone.utc).strftime("%m%d%H%M%S")

    sent = errors = 0
    with httpx.Client(
        base_url=API_URL, timeout=15, headers={"X-Tenant-API-Key": api_key}
    ) as client:
        for n, raw in enumerate(rows, 1):
            row = normalize(raw)
            row["items"] = items_by_order.get(row["order_id"], [])
            if fresh_ids:
                row["order_id"] = f"{row['order_id']}-L{run_id}"
                row["event_id"] = f"{row['event_id']}-L{run_id}"
            if stamp_now:
                row["event_timestamp"] = datetime.now(timezone.utc).isoformat()
            resp = client.post("/webhook/order-created", json=row)
            if resp.status_code == 200:
                sent += 1
            else:
                errors += 1
            print(f"[{n}/{len(rows)}] {row['order_id']} -> {resp.status_code}", flush=True)
            if resp.status_code != 200:
                print("   ", resp.text[:300])
            time.sleep(random.uniform(min_delay, max_delay))
    print(f"Terminé : {sent} envoyées, {errors} en erreur.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Rejoue checkout_events.csv en flux continu")
    p.add_argument("--limit", type=int, default=None, help="nombre de commandes à envoyer")
    p.add_argument("--min-delay", type=float, default=2.0)
    p.add_argument("--max-delay", type=float, default=8.0)
    p.add_argument("--keep-ids", action="store_true", help="conserve les order_id d'origine")
    p.add_argument("--now", action="store_true", help="horodate avec l'heure courante")
    a = p.parse_args()
    simulate_live_traffic(
        min_delay=a.min_delay,
        max_delay=a.max_delay,
        limit=a.limit,
        fresh_ids=not a.keep_ids,
        stamp_now=a.now,
    )
