"""Rapports analytiques du dashboard Vue : vue d'ensemble, commandes, produits, clients, direct.

Règles communes (comme Metorik) :
- seules les commandes réussies comptent dans le CA (statut différent de 'cancelled') ;
- la période est [from, to] inclus, la comparaison est soit la période précédente de même
  durée (`prev`), soit les mêmes dates un an plus tôt (`year`) ;
- tout est filtré par tenant (clé API), jamais de donnée d'un autre vendeur.
"""

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


# --------------------------------------------------------------------------- périodes
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
        raise HTTPException(422, "Période trop longue (10 ans maximum)")
    return d1, d2


def day_bounds(d1: date, d2: date) -> tuple[datetime, datetime]:
    """Bornes [début, fin[ en timestamps pour la période de jours [d1, d2]."""
    return datetime.combine(d1, dtime.min), datetime.combine(d2 + timedelta(days=1), dtime.min)


def shift_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 février
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
    """Regroupe des lignes journalières (date, ca, commandes) par semaine ou par mois."""
    if group == "day":
        return rows
    buckets: dict[date, list] = {}
    for day, revenue, orders in rows:
        key = day - timedelta(days=day.weekday()) if group == "week" else day.replace(day=1)
        bucket = buckets.setdefault(key, [0, 0])
        bucket[0] += revenue
        bucket[1] += orders
    return [(key, v[0], v[1]) for key, v in sorted(buckets.items())]


# --------------------------------------------------------------------------- requêtes de base
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


# --------------------------------------------------------------------------- compte et bornes
@router.get("/auth/me", tags=["auth"], summary="Valide la clé API et renvoie la boutique")
def whoami(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM tenants WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
    return {"tenant_id": tenant_id, "name": row[0] if row else "Boutique"}


@router.get("/reports/bounds", tags=["reports"], summary="Première et dernière date de commande")
def bounds(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MIN(DATE(order_purchase_timestamp)), MAX(DATE(order_purchase_timestamp)) "
            "FROM orders o WHERE tenant_id = %s AND " + OK_STATUS,
            (tenant_id,),
        )
        lo, hi = cur.fetchone()
    return {"min": lo.isoformat() if lo else None, "max": hi.isoformat() if hi else None}


# --------------------------------------------------------------------------- vue d'ensemble
@router.get("/reports/overview", tags=["reports"], summary="Vue d'ensemble avec comparaison")
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


@router.get("/reports/revenue", tags=["reports"], summary="Revenus par jour, semaine ou mois")
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


# --------------------------------------------------------------------------- commandes
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


@router.get("/orders", tags=["orders"], summary="Liste paginée et filtrable des commandes")
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
            f"o.order_total_amount, c.country {ORDER_FROM} WHERE {where} "
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
                "status": st,
                "date": ts.isoformat() if ts else None,
                "total": int(amount or 0),
                "country": country_,
                "items": int(counts.get(oid, 0)),
            }
            for oid, cid, st, ts, amount, country_ in rows
        ],
    }


@router.get("/orders/export", tags=["orders"], summary="Export CSV des commandes filtrées")
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


# --------------------------------------------------------------------------- produits
PRODUCT_SORTS = {"units", "revenue", "margin", "margin_pct", "stock", "product_id", "category"}


@router.get("/reports/products", tags=["reports"], summary="Performance des produits")
def products_report(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    q: str | None = None,
    sort: str = "revenue",
    dir: str = "desc",
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    d1, d2 = need_period(date_from, date_to)
    lo, hi = day_bounds(d1, d2)
    params = {"t": tenant_id, "lo": lo, "hi": hi, "q": f"%{q}%" if q else None}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.product_id, p.category, COALESCE(p.product_cost, 0), "
            "COALESCE(p.stock_quantity, 0), COALESCE(p.stock_alert_threshold, 0), "
            "COALESCE(s.units, 0), COALESCE(s.revenue, 0) FROM products p LEFT JOIN ("
            "SELECT oi.product_id, COUNT(*) AS units, SUM(oi.item_total) AS revenue "
            "FROM order_items oi JOIN orders o ON o.tenant_id = oi.tenant_id "
            "AND o.order_id = oi.order_id WHERE oi.tenant_id = %(t)s AND "
            + OK_STATUS
            + " AND o.order_purchase_timestamp >= %(lo)s AND o.order_purchase_timestamp < %(hi)s "
            "GROUP BY oi.product_id) s ON s.product_id = p.product_id WHERE p.tenant_id = %(t)s "
            "AND (%(q)s::text IS NULL OR p.product_id ILIKE %(q)s OR p.category ILIKE %(q)s)",
            params,
        )
        rows = cur.fetchall()
    items = []
    for pid, category, cost, stock, threshold, units, revenue in rows:
        margin = int(revenue) - int(units) * int(cost)
        items.append(
            {
                "product_id": pid,
                "category": category,
                "units": int(units),
                "revenue": int(revenue),
                "margin": margin,
                "margin_pct": round(margin / revenue * 100, 1) if revenue else None,
                "stock": int(stock),
                "stock_status": stock_status(int(stock), int(threshold)),
            }
        )
    key = sort if sort in PRODUCT_SORTS else "revenue"
    items.sort(
        key=lambda x: (x[key] is None, x[key] if x[key] is not None else 0),
        reverse=dir.lower() != "asc",
    )
    return {
        "totals": {
            "products": len(items),
            "sold_products": sum(1 for i in items if i["units"] > 0),
            "units": sum(i["units"] for i in items),
            "revenue": sum(i["revenue"] for i in items),
            "margin": sum(i["margin"] for i in items if i["units"] > 0),
        },
        "items": items,
    }


# --------------------------------------------------------------------------- clients
CUSTOMER_STATS = (
    "WITH stats AS (SELECT c.customer_id, c.city, c.country, "
    "COUNT(o.order_id) FILTER (WHERE o.order_status != 'cancelled') AS orders, "
    "COALESCE(SUM(o.order_total_amount) FILTER (WHERE o.order_status != 'cancelled'), 0) AS spent, "
    "MIN(o.order_purchase_timestamp) FILTER (WHERE o.order_status != 'cancelled') AS first_order, "
    "MAX(o.order_purchase_timestamp) FILTER (WHERE o.order_status != 'cancelled') AS last_order "
    "FROM customers c LEFT JOIN orders o ON o.tenant_id = c.tenant_id "
    "AND o.customer_id = c.customer_id WHERE c.tenant_id = %(t)s "
    "GROUP BY c.customer_id, c.city, c.country) "
)
CUSTOMER_SORTS = {
    "spent": "spent",
    "orders": "orders",
    "last_order": "last_order",
    "first_order": "first_order",
    "customer": "customer_id",
    "country": "country",
}


def customer_row(row) -> dict:
    cid, city, country, orders, spent, first, last = row[:7]
    return {
        "customer_id": cid,
        "city": city,
        "country": country,
        "orders": int(orders),
        "spent": int(spent),
        "aov": round(int(spent) / int(orders)) if orders else 0,
        "first_order": first.isoformat() if first else None,
        "last_order": last.isoformat() if last else None,
    }


@router.get("/customers", tags=["customers"], summary="Clients : liste, segments et synthèse")
def list_customers(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    segment: str = "all",
    q: str | None = None,
    sort: str = "spent",
    dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    d1, d2 = parse_day(date_from, "from"), parse_day(date_to, "to")
    params: dict = {"t": tenant_id, "q": f"%{q}%" if q else None}
    where = [
        "(%(q)s::text IS NULL OR customer_id ILIKE %(q)s OR city ILIKE %(q)s "
        "OR country ILIKE %(q)s)"
    ]
    if segment == "repeat":
        where.append("orders >= 2")
    elif segment == "single":
        where.append("orders = 1")
    elif segment == "vip":
        where.append(
            "orders > 0 AND spent >= (SELECT COALESCE(PERCENTILE_CONT(0.9) WITHIN GROUP "
            "(ORDER BY spent), 0) FROM stats WHERE orders > 0)"
        )
    elif segment == "new" and d1 and d2:
        params["lo"], params["hi"] = day_bounds(d1, d2)
        where.append("first_order >= %(lo)s AND first_order < %(hi)s")
    elif segment == "inactive":
        where.append(
            "orders > 0 AND last_order < (SELECT MAX(last_order) FROM stats) "
            "- interval '90 days'"
        )
    order_by = CUSTOMER_SORTS.get(sort, "spent")
    direction = "ASC" if dir.lower() == "asc" else "DESC"
    with conn.cursor() as cur:
        cur.execute(
            CUSTOMER_STATS
            + "SELECT *, COUNT(*) OVER () AS total FROM stats WHERE "
            + " AND ".join(where)
            + f" ORDER BY {order_by} {direction} NULLS LAST, customer_id "
            "LIMIT %(limit)s OFFSET %(off)s",
            {**params, "limit": page_size, "off": (page - 1) * page_size},
        )
        rows = cur.fetchall()
        cur.execute(
            CUSTOMER_STATS + "SELECT COUNT(*) FILTER (WHERE orders > 0), "
            "COUNT(*) FILTER (WHERE orders >= 2), "
            "COALESCE(AVG(spent) FILTER (WHERE orders > 0), 0), "
            "COUNT(*) FROM stats",
            {"t": tenant_id},
        )
        buyers, repeaters, avg_ltv, everyone = cur.fetchone()
        new_in_period = returning_in_period = None
        if d1 and d2:
            lo, hi = day_bounds(d1, d2)
            cur.execute(
                CUSTOMER_STATS + "SELECT COUNT(*) FILTER (WHERE first_order >= %(lo)s AND "
                "first_order < %(hi)s), COUNT(*) FILTER (WHERE first_order < %(lo)s AND "
                "EXISTS (SELECT 1 FROM orders o WHERE o.tenant_id = %(t)s AND "
                "o.customer_id = stats.customer_id AND o.order_status != 'cancelled' AND "
                "o.order_purchase_timestamp >= %(lo)s AND o.order_purchase_timestamp < %(hi)s)) "
                "FROM stats",
                {"t": tenant_id, "lo": lo, "hi": hi},
            )
            new_in_period, returning_in_period = cur.fetchone()
    return {
        "total": int(rows[0][7]) if rows else 0,
        "page": page,
        "page_size": page_size,
        "summary": {
            "customers": int(everyone),
            "buyers": int(buyers),
            "repeat_rate": round(repeaters / buyers * 100, 1) if buyers else 0,
            "avg_ltv": round(float(avg_ltv)),
            "new_in_period": new_in_period,
            "returning_in_period": returning_in_period,
        },
        "items": [customer_row(r) for r in rows],
    }


@router.get("/customers/{customer_id}", tags=["customers"], summary="Fiche client")
def customer_detail(
    customer_id: str, tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)
):
    with conn.cursor() as cur:
        cur.execute(
            CUSTOMER_STATS.replace(
                "WHERE c.tenant_id = %(t)s", "WHERE c.tenant_id = %(t)s AND c.customer_id = %(c)s"
            )
            + "SELECT * FROM stats",
            {"t": tenant_id, "c": customer_id},
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Client introuvable")
        cur.execute(
            "SELECT o.order_id, o.order_status, o.order_purchase_timestamp, o.order_total_amount "
            "FROM orders o WHERE o.tenant_id = %s AND o.customer_id = %s "
            "ORDER BY o.order_purchase_timestamp DESC NULLS LAST LIMIT 50",
            (tenant_id, customer_id),
        )
        orders = cur.fetchall()
        cur.execute(
            "SELECT oi.product_id, p.category, COUNT(*), SUM(oi.item_total) FROM order_items oi "
            "JOIN orders o ON o.tenant_id = oi.tenant_id AND o.order_id = oi.order_id "
            "LEFT JOIN products p ON p.tenant_id = oi.tenant_id AND p.product_id = oi.product_id "
            "WHERE o.tenant_id = %s AND o.customer_id = %s AND o.order_status != 'cancelled' "
            "GROUP BY oi.product_id, p.category ORDER BY 4 DESC LIMIT 10",
            (tenant_id, customer_id),
        )
        products = cur.fetchall()
        cur.execute(
            "SELECT date_trunc('month', order_purchase_timestamp)::date, SUM(order_total_amount) "
            "FROM orders WHERE tenant_id = %s AND customer_id = %s AND order_status != 'cancelled' "
            "GROUP BY 1 ORDER BY 1",
            (tenant_id, customer_id),
        )
        monthly = cur.fetchall()
    return {
        **customer_row(row),
        "orders_list": [
            {"order_id": o, "status": s, "date": t.isoformat() if t else None, "total": int(a or 0)}
            for o, s, t, a in orders
        ],
        "products": [
            {"product_id": p, "category": c, "units": int(n), "revenue": int(r)}
            for p, c, n, r in products
        ],
        "monthly": {
            "labels": [m.isoformat() for m, _ in monthly],
            "revenue": [int(v) for _, v in monthly],
        },
    }


# --------------------------------------------------------------------------- fraude et direct
@router.get("/fraud/summary", tags=["fraud"], summary="Synthèse fraude et décisions du vendeur")
def fraud_summary(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    r = get_redis()
    stats = r.hgetall(f"fraud_stats:{tenant_id}")
    scored, flagged = int(stats.get("scored", 0)), int(stats.get("flagged", 0))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT d.action, COUNT(*), COALESCE(SUM(o.order_total_amount), 0) "
            "FROM fraud_decisions d "
            "LEFT JOIN orders o ON o.tenant_id = d.tenant_id AND o.order_id = d.order_id "
            "WHERE d.tenant_id = %s GROUP BY d.action",
            (tenant_id,),
        )
        decisions = {a: {"count": int(n), "amount": int(v)} for a, n, v in cur.fetchall()}
        cur.execute(
            "SELECT d.order_id, d.action, d.decided_at, o.order_total_amount, o.customer_id "
            "FROM fraud_decisions d LEFT JOIN orders o ON o.tenant_id = d.tenant_id "
            "AND o.order_id = d.order_id WHERE d.tenant_id = %s "
            "ORDER BY d.decided_at DESC LIMIT 20",
            (tenant_id,),
        )
        recent = [
            {
                "order_id": oid,
                "action": act,
                "decided_at": at.isoformat() if at else None,
                "amount": int(amount or 0),
                "customer_id": cust,
            }
            for oid, act, at, amount, cust in cur.fetchall()
        ]
    return {
        "pending": r.hlen(f"fraud_alerts:{tenant_id}"),
        "scored": scored,
        "flagged": flagged,
        "flag_rate": round(flagged / scored * 100, 1) if scored else 0.0,
        "blocked": decisions.get("BLOCK", {"count": 0, "amount": 0}),
        "passed": decisions.get("PASS", {"count": 0, "amount": 0}),
        "recent": recent,
    }


@router.get("/live/feed", tags=["live"], summary="Flux des dernières commandes en temps réel")
def live_feed(limit: int = Query(20, ge=1, le=100), tenant_id: str = Depends(get_current_tenant)):
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
            events.append(
                {
                    "order_id": payload.get("order_id"),
                    "customer_id": payload.get("customer_id"),
                    "amount": amount,
                    "status": payload.get("payment_status"),
                    "country": payload.get("ip_country"),
                    "items": len(payload.get("items") or []),
                    "at": datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds"),
                    "score": json.loads(alert)["score"] if alert else None,
                }
            )
    series = [
        {
            "minutes_ago": m,
            "orders": minutes.get(m, [0, 0])[0],
            "revenue": minutes.get(m, [0, 0])[1],
        }
        for m in range(29, -1, -1)
    ]
    return {"events": events, "totals": totals, "series": series, "pending_alerts": len(alerts)}


@router.get("/reports/forecast", tags=["forecast"], summary="Prévisions de ventes agrégées")
def forecast_overview(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT forecast_date, SUM(predicted_units) FROM forecasts WHERE tenant_id = %s "
            "GROUP BY forecast_date ORDER BY forecast_date",
            (tenant_id,),
        )
        daily = cur.fetchall()
        cur.execute(
            "SELECT product_id, SUM(predicted_units) FROM forecasts WHERE tenant_id = %s "
            "GROUP BY product_id ORDER BY 2 DESC LIMIT 10",
            (tenant_id,),
        )
        top = cur.fetchall()
    return {
        "labels": [d.isoformat() for d, _ in daily],
        "units": [int(u) for _, u in daily],
        "top_products": [{"product_id": p, "units": int(u)} for p, u in top],
    }
