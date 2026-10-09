"""Routes de l'API : webhook, KPI, stocks, fraude, prévisions, assistant RAG."""

import json
import logging
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import csv
import io

from src.api.deps import get_current_tenant, get_db
from src.api.schemas import AssistantQuery, CheckoutEvent, FraudDecision
from src.batch.stock import stock_status
from src.rag.assistant import generate_rag_response, search_similar
from src.rag.llm import LLMError
from src.storage.db_connection import get_mongo_db
from src.streaming.redis_client import get_redis

log = logging.getLogger("api")

webhook_router = APIRouter(tags=["webhook"])
router = APIRouter(prefix="/api/v1")


# --------------------------------------------------------------------------- webhook
@webhook_router.post(
    "/webhook/order-created",
    summary="Reçoit un événement de checkout",
    description="Écrit l'événement dans MongoDB (zone Landing) puis le publie dans Redis Streams.",
)
def receive_checkout_event(event: CheckoutEvent, tenant_id: str = Depends(get_current_tenant)):
    payload = event.model_dump()
    payload["tenant_id"] = tenant_id
    get_mongo_db()["checkout_events"].insert_one({**payload})
    get_redis().xadd(
        "checkout_events", {"data": json.dumps(payload)}, maxlen=100_000, approximate=True
    )
    return {"status": "received", "tenant_id": tenant_id, "order_id": event.order_id}


# --------------------------------------------------------------------------- KPI
@router.get(
    "/kpi/summary",
    tags=["kpi"],
    summary="4 indicateurs clés du tenant",
    description="CA (XOF), nombre de commandes, panier moyen et taux de commandes suspectes.",
)
def kpi_summary(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "COALESCE((SELECT revenue_xof FROM v_revenue_by_tenant WHERE tenant_id = %(t)s), 0), "
            "COALESCE((SELECT avg_basket_xof FROM v_average_basket WHERE tenant_id = %(t)s), 0), "
            "(SELECT COUNT(*) FROM orders WHERE tenant_id = %(t)s AND order_status != 'cancelled')",
            {"t": tenant_id},
        )
        revenue, basket, count = cur.fetchone()
    stats = get_redis().hgetall(f"fraud_stats:{tenant_id}")
    scored, flagged = int(stats.get("scored", 0)), int(stats.get("flagged", 0))
    return {
        "revenue_xof": int(revenue),
        "order_count": int(count),
        "avg_basket_xof": float(basket),
        "fraud_rate": (flagged / scored * 100) if scored else 0.0,
    }


@router.get("/kpi/top-products", tags=["kpi"], summary="Top produits avec nom (catégorie)")
def kpi_top_products(
    limit: int = Query(10, ge=1, le=50),
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT oi.product_id,
                   COALESCE(NULLIF(p.product_name, ''), NULLIF(p.category, ''), oi.product_id) AS product_name,
                   COALESCE(p.category, '—') AS category,
                   COUNT(DISTINCT oi.order_id) AS units_sold,
                   COALESCE(SUM(oi.item_total), 0) AS revenue_xof
            FROM order_items oi
            JOIN orders o USING (tenant_id, order_id)
            LEFT JOIN products p ON p.tenant_id = oi.tenant_id AND p.product_id = oi.product_id
            WHERE oi.tenant_id = %s AND o.order_status != 'cancelled'
            GROUP BY oi.product_id, p.product_name, p.category
            ORDER BY units_sold DESC
            LIMIT %s
            """,
            (tenant_id, limit),
        )
        return [
            {
                "product_id": pid,
                "product_name": name,
                "category": cat,
                "units_sold": int(u),
                "revenue_xof": int(rev),
            }
            for pid, name, cat, u, rev in cur.fetchall()
        ]

@router.get("/kpi/timeseries", tags=["kpi"], summary="CA et commandes par jour/mois/année")
def kpi_timeseries(
    grain: str = Query("day", pattern="^(day|month|year)$"),
    days: int = Query(90, ge=1, le=3650),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    if grain == "day":
        trunc = "day"
    elif grain == "month":
        trunc = "month"
    else:
        trunc = "year"
    with conn.cursor() as cur:
        if year and month:
            cur.execute(
                f"""
                SELECT DATE_TRUNC(%s, order_purchase_timestamp)::date AS d,
                       COUNT(*) AS orders,
                       COALESCE(SUM(order_total_amount), 0) AS revenue
                FROM orders
                WHERE tenant_id = %s AND order_status != 'cancelled'
                  AND EXTRACT(YEAR FROM order_purchase_timestamp) = %s
                  AND EXTRACT(MONTH FROM order_purchase_timestamp) = %s
                GROUP BY 1 ORDER BY 1
                """,
                (trunc, tenant_id, year, month),
            )
        elif year:
            cur.execute(
                f"""
                SELECT DATE_TRUNC(%s, order_purchase_timestamp)::date AS d,
                       COUNT(*) AS orders,
                       COALESCE(SUM(order_total_amount), 0) AS revenue
                FROM orders
                WHERE tenant_id = %s AND order_status != 'cancelled'
                  AND EXTRACT(YEAR FROM order_purchase_timestamp) = %s
                GROUP BY 1 ORDER BY 1
                """,
                (trunc, tenant_id, year),
            )
        else:
            cur.execute(
                f"""
                SELECT DATE_TRUNC(%s, order_purchase_timestamp)::date AS d,
                       COUNT(*) AS orders,
                       COALESCE(SUM(order_total_amount), 0) AS revenue
                FROM orders
                WHERE tenant_id = %s AND order_status != 'cancelled'
                  AND order_purchase_timestamp >= NOW() - (%s || ' days')::interval
                GROUP BY 1 ORDER BY 1
                """,
                (trunc, tenant_id, str(days)),
            )
        rows = cur.fetchall()
    return [
        {"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "orders": int(o), "revenue_xof": int(r)}
        for d, o, r in rows
    ]


@router.get("/kpi/by-category", tags=["kpi"], summary="CA et unités par catégorie")
def kpi_by_category(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(NULLIF(p.category, ''), 'Sans catégorie') AS category,
                   COUNT(DISTINCT oi.order_id) AS orders,
                   COALESCE(SUM(oi.item_total), 0) AS revenue_xof,
                   COUNT(*) AS lines
            FROM order_items oi
            JOIN orders o USING (tenant_id, order_id)
            LEFT JOIN products p ON p.tenant_id = oi.tenant_id AND p.product_id = oi.product_id
            WHERE oi.tenant_id = %s AND o.order_status != 'cancelled'
            GROUP BY 1 ORDER BY revenue_xof DESC
            LIMIT 15
            """,
            (tenant_id,),
        )
        return [
            {"category": c, "orders": int(o), "revenue_xof": int(r), "lines": int(n)}
            for c, o, r, n in cur.fetchall()
        ]


@router.get("/kpi/new-vs-returning", tags=["kpi"], summary="Nouveaux vs clients récurrents")
def kpi_new_vs_returning(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH cust AS (
              SELECT customer_id, COUNT(*) AS n_orders, SUM(order_total_amount) AS spent
              FROM orders
              WHERE tenant_id = %s AND order_status != 'cancelled'
              GROUP BY customer_id
            )
            SELECT
              COUNT(*) FILTER (WHERE n_orders = 1) AS new_customers,
              COUNT(*) FILTER (WHERE n_orders > 1) AS returning_customers,
              COALESCE(SUM(spent) FILTER (WHERE n_orders = 1), 0) AS new_revenue,
              COALESCE(SUM(spent) FILTER (WHERE n_orders > 1), 0) AS returning_revenue
            FROM cust
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
    return {
        "new_customers": int(row[0] or 0),
        "returning_customers": int(row[1] or 0),
        "new_revenue_xof": int(row[2] or 0),
        "returning_revenue_xof": int(row[3] or 0),
    }


@router.get("/customers/segments", tags=["customers"], summary="Segments clients type Metorik")
def customer_segments(
    min_orders: int | None = None,
    max_orders: int | None = None,
    min_spent: int | None = None,
    max_spent: int | None = None,
    country: str | None = None,
    city: str | None = None,
    segment: str | None = Query(None, description="one_order|repeat|high_value|at_risk|champions"),
    limit: int = Query(100, ge=1, le=500),
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    """Filtres inspirés Metorik : dépenses, nb commandes, géographie, segments prédéfinis."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.customer_id, c.city, c.country,
                   COUNT(o.order_id) AS order_count,
                   COALESCE(SUM(o.order_total_amount), 0) AS lifetime_value,
                   MAX(o.order_purchase_timestamp) AS last_order_at,
                   MIN(o.order_purchase_timestamp) AS first_order_at
            FROM customers c
            LEFT JOIN orders o ON o.tenant_id = c.tenant_id AND o.customer_id = c.customer_id
              AND o.order_status != 'cancelled'
            WHERE c.tenant_id = %s
            GROUP BY c.customer_id, c.city, c.country
            """,
            (tenant_id,),
        )
        rows = cur.fetchall()

    out = []
    for cid, city_v, country_v, n, ltv, last_at, first_at in rows:
        n = int(n or 0)
        ltv = int(ltv or 0)
        # preset segments
        label = "other"
        if n == 0:
            label = "never_ordered"
        elif n == 1:
            label = "one_order"
        elif n >= 5 and ltv >= 500_000:
            label = "champions"
        elif n >= 2:
            label = "repeat"
        if n >= 1 and ltv >= 1_000_000:
            label = "high_value"
        # at_risk: had orders but last > 180d
        if last_at and n >= 1:
            from datetime import datetime, timezone
            last = last_at if last_at.tzinfo else last_at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - last).days > 180 and n >= 2:
                label = "at_risk"

        if segment and label != segment and not (segment == "repeat" and n >= 2):
            if segment == "repeat" and n >= 2 and label in ("repeat", "champions", "high_value", "at_risk"):
                pass
            elif segment != label:
                continue
        if min_orders is not None and n < min_orders:
            continue
        if max_orders is not None and n > max_orders:
            continue
        if min_spent is not None and ltv < min_spent:
            continue
        if max_spent is not None and ltv > max_spent:
            continue
        if country and (country_v or "").lower() != country.lower():
            continue
        if city and (city_v or "").lower() != city.lower():
            continue
        out.append({
            "customer_id": cid,
            "city": city_v,
            "country": country_v,
            "order_count": n,
            "lifetime_value_xof": ltv,
            "last_order_at": last_at.isoformat() if last_at else None,
            "first_order_at": first_at.isoformat() if first_at else None,
            "segment": label,
        })

    out.sort(key=lambda x: x["lifetime_value_xof"], reverse=True)
    summary = {
        "count": len(out),
        "total_ltv_xof": sum(x["lifetime_value_xof"] for x in out),
        "avg_ltv_xof": int(sum(x["lifetime_value_xof"] for x in out) / len(out)) if out else 0,
        "avg_orders": round(sum(x["order_count"] for x in out) / len(out), 2) if out else 0,
    }
    return {"summary": summary, "customers": out[:limit]}


@router.get("/customers/segment-stats", tags=["customers"], summary="Stats des segments prédéfinis")
def customer_segment_stats(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    data = customer_segments(limit=500, tenant_id=tenant_id, conn=conn)
    buckets = {}
    for c in data["customers"]:
        buckets.setdefault(c["segment"], {"count": 0, "ltv": 0})
        buckets[c["segment"]]["count"] += 1
        buckets[c["segment"]]["ltv"] += c["lifetime_value_xof"]
    return [
        {"segment": k, "customers": v["count"], "total_ltv_xof": v["ltv"]}
        for k, v in sorted(buckets.items(), key=lambda x: -x[1]["ltv"])
    ]


def _csv_response(filename: str, headers: list[str], rows: list[list]):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/products", tags=["export"], summary="Export CSV top produits")
def export_products(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    rows = kpi_top_products(limit=50, tenant_id=tenant_id, conn=conn)
    return _csv_response(
        "products.csv",
        ["product_id", "product_name", "category", "units_sold", "revenue_xof"],
        [[r["product_id"], r["product_name"], r["category"], r["units_sold"], r["revenue_xof"]] for r in rows],
    )


@router.get("/export/customers", tags=["export"], summary="Export CSV clients (filtres segment)")
def export_customers(
    segment: str | None = None,
    country: str | None = None,
    min_spent: int | None = None,
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    data = customer_segments(
        segment=segment, country=country, min_spent=min_spent, limit=500, tenant_id=tenant_id, conn=conn
    )
    return _csv_response(
        "customers.csv",
        ["customer_id", "city", "country", "order_count", "lifetime_value_xof", "segment", "last_order_at"],
        [
            [c["customer_id"], c["city"], c["country"], c["order_count"], c["lifetime_value_xof"], c["segment"], c["last_order_at"]]
            for c in data["customers"]
        ],
    )


@router.get("/export/timeseries", tags=["export"], summary="Export CSV série temporelle CA")
def export_timeseries(
    grain: str = Query("day", pattern="^(day|month|year)$"),
    days: int = 365,
    year: int | None = None,
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    rows = kpi_timeseries(grain=grain, days=days, year=year, tenant_id=tenant_id, conn=conn)
    return _csv_response(
        "timeseries.csv",
        ["date", "orders", "revenue_xof"],
        [[r["date"], r["orders"], r["revenue_xof"]] for r in rows],
    )



# --------------------------------------------------------------------------- stocks
@router.get(
    "/stock/status",
    tags=["stock"],
    summary="État des stocks (RUPTURE / ALERTE / OK)",
    description="Le seuil vient de products.stock_alert_threshold. Les plus critiques d'abord.",
)
def stock_overview(
    limit: int = 200, tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)
):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT product_id, category, stock_quantity, stock_alert_threshold FROM products "
            "WHERE tenant_id = %s",
            (tenant_id,),
        )
        rows = cur.fetchall()
    order = {"RUPTURE": 0, "ALERTE": 1, "OK": 2}
    out = [
        {
            "product_id": pid,
            "product_name": (cat or pid),
            "category": cat,
            "stock_quantity": int(qty or 0),
            "stock_alert_threshold": int(thr or 0),
            "status": stock_status(int(qty or 0), int(thr or 0)),
        }
        for pid, cat, qty, thr in rows
    ]
    out.sort(key=lambda x: (order[x["status"]], x["stock_quantity"]))
    return out[:limit]


# --------------------------------------------------------------------------- fraude
@router.get(
    "/fraud/alerts",
    tags=["fraud"],
    summary="Alertes de fraude en attente",
    description="Uniquement les alertes du tenant authentifié (HASH Redis par tenant, 24 h).",
)
def get_alerts(tenant_id: str = Depends(get_current_tenant)):
    from src.ml.fraud_detection.scoring import risk_level

    raw = get_redis().hgetall(f"fraud_alerts:{tenant_id}")
    alerts = []
    for order_id, value in raw.items():
        data = json.loads(value)
        alerts.append({"order_id": order_id, **data, "risk": risk_level(data["score"])})
    return sorted(alerts, key=lambda a: a["score"], reverse=True)


@router.post(
    "/fraud/decision",
    tags=["fraud"],
    summary="Décision vendeur : BLOCK ou PASS",
    description="Enregistre la décision dans fraud_decisions et retire l'alerte de la liste.",
)
def decide(body: FraudDecision, tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    r = get_redis()
    key = f"fraud_alerts:{tenant_id}"
    if not r.hexists(key, body.order_id):
        raise HTTPException(404, "Alerte introuvable pour ce tenant")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO fraud_decisions (tenant_id, order_id, action) VALUES (%s, %s, %s) "
            "ON CONFLICT (tenant_id, order_id) DO UPDATE SET action = EXCLUDED.action, "
            "decided_at = now()",
            (tenant_id, body.order_id, body.action),
        )
    conn.commit()
    r.hdel(key, body.order_id)
    return {"status": "recorded"}


# --------------------------------------------------------------------------- prévisions
@router.get("/forecast/products", tags=["forecast"], summary="Produits ayant une prévision")
def forecast_products(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT product_id, SUM(predicted_units) AS total FROM forecasts WHERE tenant_id = %s "
            "GROUP BY product_id ORDER BY total DESC",
            (tenant_id,),
        )
        return [row[0] for row in cur.fetchall()]


@router.get(
    "/forecast/{product_id}",
    tags=["forecast"],
    summary="Historique (90 j) et prévision d'un produit, en unités vendues",
)
def forecast_product(
    product_id: str, tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)
):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT forecast_date, predicted_units FROM forecasts "
            "WHERE tenant_id = %s AND product_id = %s ORDER BY forecast_date",
            (tenant_id, product_id),
        )
        forecast = [{"date": d.isoformat(), "predicted_units": int(u)} for d, u in cur.fetchall()]
        if not forecast:
            raise HTTPException(404, "Aucune prévision pour ce produit")
        first = datetime.fromisoformat(forecast[0]["date"])
        cur.execute(
            "SELECT DATE(o.order_purchase_timestamp) AS d, COUNT(*) FROM order_items oi "
            "JOIN orders o USING (tenant_id, order_id) "
            "WHERE oi.tenant_id = %s AND oi.product_id = %s AND o.order_status != 'cancelled' "
            "AND o.order_purchase_timestamp >= %s AND o.order_purchase_timestamp < %s "
            "GROUP BY d ORDER BY d",
            (tenant_id, product_id, first - timedelta(days=90), first),
        )
        history = [{"date": d.isoformat(), "units": int(u)} for d, u in cur.fetchall()]
    return {"product_id": product_id, "history": history, "forecast": forecast}


# --------------------------------------------------------------------------- assistant RAG
@router.post(
    "/assistant/query",
    tags=["assistant"],
    summary="Pose une question à l'assistant (RAG)",
    description="Recherche sémantique dans les avis/tickets du tenant puis réponse du LLM.",
)
def query_assistant(
    body: AssistantQuery, tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)
):
    start = time.perf_counter()
    context = search_similar(body.question, tenant_id, conn)
    try:
        answer = generate_rag_response(body.question, context)
    except LLMError as exc:
        raise HTTPException(503, str(exc))
    log.info("rag_ms=%.0f sources=%d", (time.perf_counter() - start) * 1000, len(context))
    return {"answer": answer, "sources_count": len(context)}
