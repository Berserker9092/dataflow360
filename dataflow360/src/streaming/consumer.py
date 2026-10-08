"""Fraud Consumer (étape 49) : Redis Streams -> PostgreSQL (commande + stock) -> scoring."""

import json
import logging
import sys
import time

from redis.exceptions import ResponseError

from src.ml.fraud_detection.scoring import score_event
from src.storage.db_connection import get_pg_connection
from src.storage.warehouse_writer import upsert_order
from src.streaming.redis_client import get_redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fraud-consumer")

STREAM, GROUP, CONSUMER = "checkout_events", "fraud_group", "consumer-1"
DLQ = "checkout_events_dlq"
METRICS_KEY = "metrics:scoring_ms"


def ensure_group(r, start_id: str = "0") -> None:
    try:
        r.xgroup_create(STREAM, GROUP, id=start_id, mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def handle_event(event: dict, conn, r) -> None:
    upsert_order(event, conn)  # la commande existe dans le warehouse
    # déduplication : un message rejoué ne décrémente pas le stock deux fois
    done_key = f"done:{event['tenant_id']}:{event['order_id']}"
    if r.set(done_key, 1, nx=True, ex=86400):
        try:
            score_event(event, conn, r)
        except Exception:
            r.delete(done_key)
            raise


def process_message(r, conn, msg_id: str, fields: dict) -> None:
    start = time.perf_counter()
    try:
        event = json.loads(fields["data"])
        handle_event(event, conn, r)
        ms = (time.perf_counter() - start) * 1000
        r.lpush(METRICS_KEY, f"{ms:.0f}")
        r.ltrim(METRICS_KEY, 0, 499)
        log.info("OK order_id=%s scoring_ms=%.0f", event["order_id"], ms)
    except Exception as exc:
        conn.rollback()
        log.exception("Échec sur le message %s", msg_id)
        r.xadd(DLQ, {"data": fields.get("data", ""), "error": str(exc)[:500]})
    r.xack(STREAM, GROUP, msg_id)


def drain_pending(r, conn) -> None:
    """Retraite les messages lus mais jamais acquittés (arrêt brutal précédent)."""
    while True:
        resp = r.xreadgroup(GROUP, CONSUMER, {STREAM: "0"}, count=50)
        messages = resp[0][1] if resp else []
        if not messages:
            return
        for msg_id, fields in messages:
            process_message(r, conn, msg_id, fields)


def run(from_now: bool = False) -> None:
    r = get_redis()
    ensure_group(r, "$" if from_now else "0")
    conn = get_pg_connection()
    log.info("Consumer démarré (groupe=%s)", GROUP)
    drain_pending(r, conn)
    while True:
        if conn.closed:
            conn = get_pg_connection()
        resp = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=10, block=5000)
        for _, messages in resp or []:
            for msg_id, fields in messages:
                process_message(r, conn, msg_id, fields)


if __name__ == "__main__":
    run(from_now="--from-now" in sys.argv)
