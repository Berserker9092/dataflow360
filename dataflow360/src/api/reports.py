"""Rapports analytiques du dashboard Vue."""

import csv
import io
import json
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from src.api.deps import get_current_tenant, get_db
from src.batch.stock import stock_status
from src.streaming.redis_client import get_redis

router = APIRouter(prefix="/api/v1")

MAX_DAYS = 3660
OK_STATUS = "o.order_status != 'cancelled'"


def parse_day(value: str | None, name: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"Date invalide pour '{name}' (format AAAA-MM-JJ)")


def need_period(date_from: str | None, date_to: str | None) -> tuple[date, date]:
    d1, d2 = parse_day(date_from, "from"), parse_day(date_to, "to")
    if d1 is None or d2 is None:
        raise HTTPException(422, "Les paramètres 'from' et 'to' sont obligatoires")
    if d1 > d2:
        raise HTTPException(422, "'from' doit précéder 'to'")
    if (d2 - d1).days > MAX_DAYS:
        raise HTTPException(422, "Période trop longue")
    return d1, d2


def day_bounds(d1: date, d2: date) -> tuple[datetime, datetime]:
    return datetime.combine(d1, dtime.min), datetime.combine(d2 + timedelta(days=1), dtime.min)


def shift_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def previous_period(d1: date, d2: date, mode: str) -> tuple[date, date] | None:
    if mode == "prev":
        days = (d2 - d1).days + 1
        end = d1 - timedelta(days=1)
        return end - timedelta(days=days - 1), end
    if mode == "year":
        return shift_year(d1), shift_year(d2)
    return None


def pct_change(current: float, previous: float | None) -> float | None:
    if previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 1)


def regroup(rows: list[tuple], group: str) -> list[tuple]:
    if group == "day":
        return rows
    buckets: dict[date, list] = {}
    for day, revenue, orders in rows:
        key = day - timedelta(days=day.weekday()) if group == "week" else day.replace(day=1)
        bucket = buckets.setdefault(key, [0, 0])
        bucket[0] += revenue
        bucket[1] += orders
    return [(key, v[0], v[1]) for key, v in sorted(buckets.items())]


def daily_series(conn, tenant: str, d1: date, d2: date) -> list[tuple]:
    lo, hi = day_bounds(d1, d2)
    with conn.cursor() as cur:
        cur.execute(
            "WITH days AS (SELECT generate_series(%(a)s::date, %(b)s::date, "
            "interval '1 day')::date AS d), agg AS ("
            "SELECT DATE(order_purchase_timestamp) AS d, SUM(order_total_amount) AS rev, "
            "COUNT(*) AS n FROM orders o WHERE tenant_id = %(t)s AND "
            + OK_STATUS
            + " AND order_purchase_timestamp >= %(lo)s AND order_purchase_timestamp < %(hi)s "
            "GROUP BY 1) SELECT days.d, COALESCE(agg.rev, 0), COALESCE(agg.n, 0) "
            "FROM days LEFT JOIN agg ON agg.d = days.d ORDER BY days.d",
            {"a": d1, "b": d2, "t": tenant, "lo": lo, "hi": hi},
        )
        return [(d, int(rev), int(n)) for d, rev, n in cur.fetchall()]


def kpi_block(conn, tenant: str, d1: date, d2: date) -> dict:
    lo, hi = day_bounds(d1, d2)
    params = (tenant, lo, hi)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(order_total_amount), 0), COUNT(*), COUNT(DISTINCT customer_id) "
            "FROM orders o WHERE tenant_id = %s AND " + OK_STATUS + " AND "
            "order_purchase_timestamp >= %s AND order_purchase_timestamp < %s",
            params,
        )
        revenue, orders, customers = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM order_items oi JOIN orders o ON o.tenant_id = oi.tenant_id "
            "AND o.order_id = oi.order_id WHERE o.tenant_id = %s AND " + OK_STATUS + " AND "
            "o.order_purchase_timestamp >= %s AND o.order_purchase_timestamp < %s",
            params,
        )
        units = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM (SELECT customer_id, MIN(order_purchase_timestamp) AS f "
            "FROM orders o WHERE tenant_id = %s AND " + OK_STATUS + " GROUP BY customer_id) x "
            "WHERE f >= %s AND f < %s",
            params,
        )
        new_customers = cur.fetchone()[0]
    revenue, orders = int(revenue), int(orders)
    return {
        "revenue": revenue,
        "orders": orders,
        "aov": round(revenue / orders) if orders else 0,
        "customers": int(customers),
        "new_customers": int(new_customers),
        "units": int(units),
    }


def breakdown(conn, sql: str, params: dict) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {"label": label if label else "Inconnu", "revenue": int(rev), "orders": int(n)}
            for label, rev, n in cur.fetchall()
        ]


@router.get("/auth/me", tags=["auth"])
def whoami(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tenant_id, name, email, company_name, contact_name, phone, country "
            "FROM tenants WHERE tenant_id = %s",
            (tenant_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Tenant introuvable")
    return {
        "tenant_id": str(row[0]),
        "name": row[1],
        "email": row[2],
        "company_name": row[3],
        "contact_name": row[4],
        "phone": row[5],
        "country": row[6],
    }


@router.get("/reports/bounds", tags=["reports"])
def bounds(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MIN(DATE(order_purchase_timestamp)), MAX(DATE(order_purchase_timestamp)) "
            "FROM orders o WHERE tenant_id = %s AND " + OK_STATUS,
            (tenant_id,),
        )
        lo, hi = cur.fetchone()
    return {"min": lo.isoformat() if lo else None, "max": hi.isoformat() if hi else None}


@router.get("/reports/overview", tags=["reports"])
def overview(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    compare: str = "prev",
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    d1, d2 = need_period(date_from, date_to)
    prev = previous_period(d1, d2, compare)
    current = kpi_block(conn, tenant_id, d1, d2)
    previous = kpi_block(conn, tenant_id, *prev) if prev else None
    series = daily_series(conn, tenant_id, d1, d2)
    prev_series = daily_series(conn, tenant_id, *prev) if prev else []

    kpis = {
        key: {
            "value": value,
            "previous": previous[key] if previous else None,
            "delta_pct": pct_change(value, previous[key]) if previous else None,
        }
        for key, value in current.items()
    }
    lo, hi = day_bounds(d1, d2)
    base = {"t": tenant_id, "lo": lo, "hi": hi}
    window = "o.order_purchase_timestamp >= %(lo)s AND o.order_purchase_timestamp < %(hi)s"
    top_products = breakdown(
        conn,
        "SELECT oi.product_id, SUM(oi.item_total), COUNT(*) FROM order_items oi JOIN orders o "
        "ON o.tenant_id = oi.tenant_id AND o.order_id = oi.order_id WHERE o.tenant_id = %(t)s "
        f"AND {OK_STATUS} AND {window} GROUP BY oi.product_id ORDER BY 2 DESC LIMIT 10",
        base,
    )
    by_country = breakdown(
        conn,
        "SELECT c.country, SUM(o.order_total_amount), COUNT(*) FROM orders o LEFT JOIN customers c "
        "ON c.tenant_id = o.tenant_id AND c.customer_id = o.customer_id "
        f"WHERE o.tenant_id = %(t)s AND {OK_STATUS} AND {window} GROUP BY c.country "
        "ORDER BY 2 DESC LIMIT 8",
        base,
    )
    by_category = breakdown(
        conn,
        "SELECT p.category, SUM(oi.item_total), COUNT(*) FROM order_items oi JOIN orders o "
        "ON o.tenant_id = oi.tenant_id AND o.order_id = oi.order_id LEFT JOIN products p "
        "ON p.tenant_id = oi.tenant_id AND p.product_id = oi.product_id "
        f"WHERE o.tenant_id = %(t)s AND {OK_STATUS} AND {window} GROUP BY p.category "
        "ORDER BY 2 DESC LIMIT 8",
        base,
    )
    by_status = breakdown(
        conn,
        "SELECT o.order_status, COALESCE(SUM(o.order_total_amount), 0), COUNT(*) FROM orders o "
        f"WHERE o.tenant_id = %(t)s AND {window} GROUP BY o.order_status ORDER BY 3 DESC",
        base,
    )
    return {
        "period": {"from": d1.isoformat(), "to": d2.isoformat(), "days": len(series)},
        "compare": {"from": prev[0].isoformat(), "to": prev[1].isoformat()} if prev else None,
        "kpis": kpis,
        "labels": [d.isoformat() for d, _, _ in series],
        "series": {
            "revenue": [r for _, r, _ in series],
            "orders": [n for _, _, n in series],
            "aov": [round(r / n) if n else 0 for _, r, n in series],
        },
        "previous_series": {
            "revenue": [r for _, r, _ in prev_series],
            "orders": [n for _, _, n in prev_series],
            "aov": [round(r / n) if n else 0 for _, r, n in prev_series],
        },
        "top_products": top_products,
        "by_country": by_country,
        "by_category": by_category,
        "by_status": by_status,
    }


@router.get("/reports/revenue", tags=["reports"])
def revenue_report(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    group: str = "day",
    compare: str = "prev",
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    if group not in {"day", "week", "month"}:
        raise HTTPException(422, "group doit valoir day, week ou month")
    d1, d2 = need_period(date_from, date_to)
    prev = previous_period(d1, d2, compare)

    def pack(rows):
        grouped = regroup(rows, group)
        return {
            "labels": [d.isoformat() for d, _, _ in grouped],
            "revenue": [r for _, r, _ in grouped],
            "orders": [n for _, _, n in grouped],
            "aov": [round(r / n) if n else 0 for _, r, n in grouped],
        }

    current = pack(daily_series(conn, tenant_id, d1, d2))
    previous = pack(daily_series(conn, tenant_id, *prev)) if prev else None
    revenue, orders = sum(current["revenue"]), sum(current["orders"])
    return {
        "group": group,
        **current,
        "previous": previous,
        "totals": {
            "revenue": revenue,
            "orders": orders,
            "aov": round(revenue / orders) if orders else 0,
        },
    }


# === MILIEU ===
ORDER_SORTS = {
    "date": "o.order_purchase_timestamp",
    "total": "o.order_total_amount",
    "status": "o.order_status",
    "customer": "o.customer_id",
    "order": "o.order_id",
    "country": "c.country",
}


def order_filters(tenant, d1, d2, status, q, country, min_total, max_total):
    where = ["o.tenant_id = %(t)s"]
    params: dict = {"t": tenant}
    if d1 and d2:
        params["lo"], params["hi"] = day_bounds(d1, d2)
        where.append("o.order_purchase_timestamp >= %(lo)s AND o.order_purchase_timestamp < %(hi)s")
    if status == "success":
        where.append(OK_STATUS)
    elif status and status != "all":
        where.append("o.order_status = %(status)s")
        params["status"] = status
    if q:
        where.append("(o.order_id ILIKE %(q)s OR o.customer_id ILIKE %(q)s)")
        params["q"] = f"%{q}%"
    if country:
        where.append("c.country = %(country)s")
        params["country"] = country
    if min_total is not None:
        where.append("o.order_total_amount >= %(min_total)s")
        params["min_total"] = min_total
    if max_total is not None:
        where.append("o.order_total_amount <= %(max_total)s")
        params["max_total"] = max_total
    return " AND ".join(where), params


ORDER_FROM = (
    "FROM orders o LEFT JOIN customers c ON c.tenant_id = o.tenant_id "
    "AND c.customer_id = o.customer_id"
)


@router.get("/orders", tags=["orders"])
def list_orders(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    status: str = "all",
    q: str | None = None,
    country: str | None = None,
    min_total: int | None = None,
    max_total: int | None = None,
    sort: str = "date",
    dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    d1, d2 = parse_day(date_from, "from"), parse_day(date_to, "to")
    where, params = order_filters(tenant_id, d1, d2, status, q, country, min_total, max_total)
    order_by = ORDER_SORTS.get(sort, ORDER_SORTS["date"])
    direction = "ASC" if dir.lower() == "asc" else "DESC"
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*), COALESCE(SUM(o.order_total_amount), 0) {ORDER_FROM} WHERE {where}",
            params,
        )
        total, revenue = cur.fetchone()
        cur.execute(
            "SELECT o.order_id, o.customer_id, o.order_status, o.order_purchase_timestamp, "
            f"o.order_total_amount, c.country, c.full_name, c.city {ORDER_FROM} WHERE {where} "
            f"ORDER BY {order_by} {direction} NULLS LAST, o.order_id "
            "LIMIT %(limit)s OFFSET %(off)s",
            {**params, "limit": page_size, "off": (page - 1) * page_size},
        )
        rows = cur.fetchall()
        counts = {}
        if rows:
            cur.execute(
                "SELECT order_id, COUNT(*) FROM order_items WHERE tenant_id = %s "
                "AND order_id = ANY(%s) GROUP BY order_id",
                (tenant_id, [r[0] for r in rows]),
            )
            counts = dict(cur.fetchall())
    return {
        "total": int(total),
        "revenue": int(revenue),
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "order_id": oid,
                "customer_id": cid,
                "customer_name": cname,
                "customer_city": ccity,
                "customer_country": country_,
                "status": st,
                "date": ts.isoformat() if ts else None,
                "total": int(amount or 0),
                "items": int(counts.get(oid, 0)),
            }
            for oid, cid, st, ts, amount, country_, cname, ccity in rows
        ],
    }


@router.get("/orders/export", tags=["orders"])
def export_orders(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    status: str = "all",
    q: str | None = None,
    country: str | None = None,
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    d1, d2 = parse_day(date_from, "from"), parse_day(date_to, "to")
    where, params = order_filters(tenant_id, d1, d2, status, q, country, None, None)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT o.order_id, o.customer_id, o.order_status, o.order_purchase_timestamp, "
            f"o.order_total_amount, c.country {ORDER_FROM} WHERE {where} "
            "ORDER BY o.order_purchase_timestamp DESC LIMIT 50000",
            params,
        )
        rows = cur.fetchall()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["commande", "client", "statut", "date", "montant_xof", "pays"])
    writer.writerows(rows)
    return Response(
        content="\ufeff" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=commandes.csv"},
    )




# --------------------------------------------------------------------------- live (temps réel)
@router.get("/live/feed", tags=["live"], summary="Flux des dernières commandes en temps réel")
def live_feed(
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(get_current_tenant),
):
    """Lit le stream Redis checkout_events pour le temps réel."""
    r = get_redis()
    alerts = r.hgetall(f"fraud_alerts:{tenant_id}")
    now_ms = int(time.time() * 1000)
    events, minutes = [], {}
    totals = {"orders_5m": 0, "revenue_5m": 0, "orders_60m": 0, "revenue_60m": 0}

    for entry_id, fields in r.xrevrange("checkout_events", count=2000):
        try:
            payload = json.loads(fields["data"])
        except (KeyError, ValueError):
            continue
        if payload.get("tenant_id") != tenant_id:
            continue

        ms = int(entry_id.split("-")[0])
        age_min = (now_ms - ms) / 60000
        amount = int(payload.get("order_total_amount") or 0)
        ok = payload.get("payment_status") != "failed"

        if ok and age_min <= 60:
            totals["orders_60m"] += 1
            totals["revenue_60m"] += amount
            if age_min <= 5:
                totals["orders_5m"] += 1
                totals["revenue_5m"] += amount

        if ok and age_min < 30:
            slot = minutes.setdefault(int(age_min), [0, 0])
            slot[0] += 1
            slot[1] += amount

        if len(events) < limit:
            alert = alerts.get(payload.get("order_id", ""))
            events.append({
                "order_id": payload.get("order_id"),
                "customer_id": payload.get("customer_id"),
                "amount": amount,
                "status": payload.get("payment_status"),
                "country": payload.get("ip_country"),
                "items": len(payload.get("items") or []),
                "at": datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds"),
                "score": json.loads(alert)["score"] if alert else None,
            })

    series = [
        {
            "minutes_ago": m,
            "orders": minutes.get(m, [0, 0])[0],
            "revenue": minutes.get(m, [0, 0])[1],
        }
        for m in range(29, -1, -1)
    ]

    return {
        "events": events,
        "totals": totals,
        "series": series,
        "pending_alerts": len(alerts),
    }
