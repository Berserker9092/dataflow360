"""Endpoints dashboard Vue + inscription vendeur (complément de routes.py)."""

from __future__ import annotations

import csv
import io
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.deps import get_current_tenant, get_db
from src.storage.tenants import hash_api_key
from src.streaming.redis_client import get_redis

extra_router = APIRouter(prefix="/api/v1")


# --------------------------------------------------------------------------- orders
@extra_router.get("/orders", tags=["orders"])
def list_orders(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    status: str = "all",
    q: str = "",
    sort: str = "date",
    dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    sort_col = {
        "date": "o.order_purchase_timestamp",
        "status": "o.order_status",
        "amount": "o.order_total_amount",
    }.get(sort, "o.order_purchase_timestamp")
    order_dir = "ASC" if dir.lower() == "asc" else "DESC"

    where = ["o.tenant_id = %s"]
    params: list = [tenant_id]
    if status and status != "all":
        st = "cancelled" if status in ("canceled", "cancelled") else status
        where.append("o.order_status = %s")
        params.append(st)
    if from_:
        where.append("o.order_purchase_timestamp >= %s")
        params.append(from_)
    if to:
        where.append("o.order_purchase_timestamp < (%s::timestamp + interval '1 day')")
        params.append(to)
    if q:
        where.append(
            "(o.order_id ILIKE %s OR o.customer_id ILIKE %s OR EXISTS ("
            " SELECT 1 FROM customers c WHERE c.tenant_id = o.tenant_id "
            " AND c.customer_id = o.customer_id AND c.full_name ILIKE %s))"
        )
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    wsql = " AND ".join(where)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM orders o WHERE {wsql}", params)
        total = int(cur.fetchone()[0])
        cur.execute(
            f"""
            SELECT o.order_id, o.order_purchase_timestamp, o.customer_id, o.order_status,
                   o.order_total_amount,
                   COALESCE((SELECT COUNT(*) FROM order_items oi
                             WHERE oi.tenant_id = o.tenant_id AND oi.order_id = o.order_id), 0)
            FROM orders o
            WHERE {wsql}
            ORDER BY {sort_col} {order_dir}
            LIMIT %s OFFSET %s
            """,
            params + [page_size, (page - 1) * page_size],
        )
        rows = cur.fetchall()
        items = []
        for oid, ts, cid, st, amount, nitems in rows:
            status_out = "canceled" if st == "cancelled" else (st or "")
            items.append(
                {
                    "order_id": oid,
                    "date": ts.isoformat() if ts else None,
                    "customer_id": cid,
                    "status": status_out,
                    "items": int(nitems),
                    "amount": int(amount or 0),
                    "customer_name": None,
                    "customer_label": None,
                    "products": [],
                }
            )
        if not items:
            return {"items": items, "total": total, "page": page, "page_size": page_size}

        order_ids = [it["order_id"] for it in items]
        customer_ids = list({it["customer_id"] for it in items if it.get("customer_id")})

        cust_map: dict = {}
        if customer_ids:
            cur.execute(
                """
                SELECT customer_id, full_name, city, country, email, phone
                FROM customers
                WHERE tenant_id = %s AND customer_id = ANY(%s)
                """,
                (tenant_id, customer_ids),
            )
            for cid, full_name, city, country, email, phone in cur.fetchall():
                parts = [x for x in (full_name, city, country) if x]
                cust_map[cid] = {
                    "customer_name": full_name,
                    "customer_label": " · ".join(parts) if parts else (cid[:12] + "…"),
                    "email": email,
                    "phone": phone,
                    "city": city,
                    "country": country,
                }

        cur.execute(
            """
            SELECT oi.order_id,
                   COALESCE(NULLIF(p.product_name, ''), NULLIF(p.category, ''), oi.product_id)
            FROM order_items oi
            LEFT JOIN products p ON p.tenant_id = oi.tenant_id AND p.product_id = oi.product_id
            WHERE oi.tenant_id = %s AND oi.order_id = ANY(%s)
            ORDER BY oi.order_id, oi.order_item_id
            """,
            (tenant_id, order_ids),
        )
        prods: dict[str, list[str]] = {}
        for oid, pname in cur.fetchall():
            prods.setdefault(oid, []).append(pname)

        for it in items:
            c = cust_map.get(it["customer_id"])
            if c:
                it["customer_name"] = c["customer_name"]
                it["customer_label"] = c["customer_label"]
                it["customer_email"] = c.get("email")
                it["customer_city"] = c.get("city")
                it["customer_country"] = c.get("country")
            else:
                it["customer_label"] = (it["customer_id"] or "")[:12] + "…"
            it["products"] = prods.get(it["order_id"], [])

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@extra_router.get("/orders/export", tags=["orders"])
def export_orders(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    status: str = "all",
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    all_items = []
    page = 1
    while page <= 10:
        chunk = list_orders(
            from_=from_,
            to=to,
            status=status,
            q="",
            sort="date",
            dir="desc",
            page=page,
            page_size=100,
            tenant_id=tenant_id,
            conn=conn,
        )
        all_items.extend(chunk["items"])
        if len(all_items) >= chunk["total"] or not chunk["items"]:
            break
        page += 1
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["order_id", "date", "customer_id", "customer_name", "customer_label", "status", "products", "amount"]
    )
    for r in all_items:
        w.writerow(
            [
                r["order_id"],
                r["date"],
                r["customer_id"],
                r.get("customer_name"),
                r.get("customer_label"),
                r["status"],
                "; ".join(r.get("products") or []),
                r["amount"],
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="orders.csv"'},
    )


# --------------------------------------------------------------------------- live
@extra_router.get("/live/feed", tags=["live"])
def live_feed(
    limit: int = Query(14, ge=1, le=50),
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    now = datetime.utcnow()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE order_purchase_timestamp >= %s),
              COALESCE(SUM(order_total_amount) FILTER (WHERE order_purchase_timestamp >= %s), 0),
              COUNT(*) FILTER (WHERE order_purchase_timestamp >= %s),
              COALESCE(SUM(order_total_amount) FILTER (WHERE order_purchase_timestamp >= %s), 0)
            FROM orders
            WHERE tenant_id = %s AND order_status != 'cancelled'
            """,
            (
                now - timedelta(minutes=5),
                now - timedelta(minutes=5),
                now - timedelta(minutes=60),
                now - timedelta(minutes=60),
                tenant_id,
            ),
        )
        o5, r5, o60, r60 = cur.fetchone()
        cur.execute(
            """
            SELECT DATE_TRUNC('minute', order_purchase_timestamp) AS m, COUNT(*)
            FROM orders
            WHERE tenant_id = %s AND order_status != 'cancelled'
              AND order_purchase_timestamp >= %s
            GROUP BY 1 ORDER BY 1
            """,
            (tenant_id, now - timedelta(minutes=30)),
        )
        by_min = {row[0]: int(row[1]) for row in cur.fetchall()}
        series = []
        for i in range(29, -1, -1):
            m = (now - timedelta(minutes=i)).replace(second=0, microsecond=0)
            cnt = 0
            for k, v in by_min.items():
                if k and abs((k.replace(tzinfo=None) - m).total_seconds()) < 45:
                    cnt = v
                    break
            series.append({"minutes_ago": i, "orders": cnt})
        cur.execute(
            """
            SELECT o.order_id, o.order_purchase_timestamp, o.order_total_amount, o.order_status,
                   o.customer_id, c.full_name
            FROM orders o
            LEFT JOIN customers c ON c.tenant_id = o.tenant_id AND c.customer_id = o.customer_id
            WHERE o.tenant_id = %s
            ORDER BY o.order_purchase_timestamp DESC NULLS LAST
            LIMIT %s
            """,
            (tenant_id, limit),
        )
        events = []
        for oid, ts, amount, st, cid, cname in cur.fetchall():
            pay = "approved"
            if st in ("cancelled", "canceled"):
                pay = "failed"
            elif st in ("pending", "processing"):
                pay = "pending"
            events.append(
                {
                    "order_id": oid,
                    "at": ts.isoformat() if ts else None,
                    "amount": int(amount or 0),
                    "status": pay,
                    "customer_id": cid,
                    "customer_name": cname,
                }
            )
    pending = 0
    try:
        raw = get_redis().hgetall(f"fraud_alerts:{tenant_id}") or {}
        for _k, val in raw.items():
            import json

            data = json.loads(val)
            if int(data.get("score", 0)) >= 70:
                pending += 1
    except Exception:
        pass
    return {
        "totals": {
            "orders_5m": int(o5 or 0),
            "revenue_5m": int(r5 or 0),
            "orders_60m": int(o60 or 0),
            "revenue_60m": int(r60 or 0),
        },
        "series": series,
        "events": events,
        "pending_alerts": pending,
    }


# --------------------------------------------------------------------------- customer detail
@extra_router.get("/customers/{customer_id}", tags=["customers"])
def customer_detail(
    customer_id: str,
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT full_name, email, phone, city, country, state, zip_code
            FROM customers WHERE tenant_id = %s AND customer_id = %s
            """,
            (tenant_id, customer_id),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT 1 FROM orders WHERE tenant_id = %s AND customer_id = %s LIMIT 1",
                (tenant_id, customer_id),
            )
            if not cur.fetchone():
                raise HTTPException(404, "Client introuvable")
            full_name = email = phone = city = country = state = zip_code = None
        else:
            full_name, email, phone, city, country, state, zip_code = row

        cur.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(order_total_amount), 0),
                   MIN(order_purchase_timestamp), MAX(order_purchase_timestamp),
                   COALESCE(AVG(order_total_amount), 0)
            FROM orders
            WHERE tenant_id = %s AND customer_id = %s AND order_status != 'cancelled'
            """,
            (tenant_id, customer_id),
        )
        n, spent, first, last, aov = cur.fetchone()
        cur.execute(
            """
            SELECT TO_CHAR(DATE_TRUNC('month', order_purchase_timestamp), 'YYYY-MM'),
                   COALESCE(SUM(order_total_amount), 0)
            FROM orders
            WHERE tenant_id = %s AND customer_id = %s AND order_status != 'cancelled'
            GROUP BY 1 ORDER BY 1
            """,
            (tenant_id, customer_id),
        )
        monthly_rows = cur.fetchall()
        cur.execute(
            """
            SELECT oi.product_id,
                   COALESCE(NULLIF(p.product_name, ''), oi.product_id),
                   COALESCE(SUM(oi.item_total), 0) AS rev
            FROM order_items oi
            JOIN orders o USING (tenant_id, order_id)
            LEFT JOIN products p ON p.tenant_id = oi.tenant_id AND p.product_id = oi.product_id
            WHERE o.tenant_id = %s AND o.customer_id = %s AND o.order_status != 'cancelled'
            GROUP BY oi.product_id, p.product_name ORDER BY rev DESC LIMIT 10
            """,
            (tenant_id, customer_id),
        )
        products = [
            {"product_id": pid, "product_name": pname, "revenue": int(rev)}
            for pid, pname, rev in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT order_id, order_purchase_timestamp, order_status, order_total_amount
            FROM orders WHERE tenant_id = %s AND customer_id = %s
            ORDER BY order_purchase_timestamp DESC NULLS LAST LIMIT 30
            """,
            (tenant_id, customer_id),
        )
        orders_list = [
            {
                "order_id": oid,
                "date": ts.isoformat() if ts else None,
                "status": "canceled" if st == "cancelled" else st,
                "total": int(amt or 0),
            }
            for oid, ts, st, amt in cur.fetchall()
        ]
    return {
        "customer_id": customer_id,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "city": city,
        "country": country,
        "state": state,
        "zip_code": zip_code,
        "orders": int(n or 0),
        "lifetime_value": int(spent or 0),
        "aov": float(aov or 0),
        "first_order": first.isoformat() if first else None,
        "last_order": last.isoformat() if last else None,
        "monthly": {
            "labels": [r[0] for r in monthly_rows],
            "revenue": [int(r[1]) for r in monthly_rows],
        },
        "products": products,
        "orders_list": orders_list,
    }


# --------------------------------------------------------------------------- forecast courbe historique + futur
@extra_router.get("/reports/forecast", tags=["forecast"])
def report_forecast(
    grain: str = Query("day", pattern="^(day|week|month)$"),
    history_days: int = Query(90, ge=7, le=730),
    product_id: str | None = None,
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    """Historique réel + prévisions sur la même série (couleurs distinctes côté front)."""
    trunc = {"day": "day", "week": "week", "month": "month"}[grain]
    with conn.cursor() as cur:
        # Historique ventes (unités = lignes order_items)
        hist_sql = f"""
            SELECT DATE_TRUNC(%s, o.order_purchase_timestamp)::date AS d,
                   COUNT(*)::int AS units
            FROM order_items oi
            JOIN orders o USING (tenant_id, order_id)
            WHERE oi.tenant_id = %s AND o.order_status != 'cancelled'
              AND o.order_purchase_timestamp >= NOW() - (%s || ' days')::interval
        """
        params: list = [trunc, tenant_id, str(history_days)]
        if product_id:
            hist_sql += " AND oi.product_id = %s"
            params.append(product_id)
        hist_sql += " GROUP BY 1 ORDER BY 1"
        cur.execute(hist_sql, params)
        history = [
            {"date": d.isoformat(), "units": int(u), "kind": "history"} for d, u in cur.fetchall()
        ]

        fc_sql = f"""
            SELECT DATE_TRUNC(%s, forecast_date)::date AS d,
                   COALESCE(SUM(predicted_units), 0)::int
            FROM forecasts
            WHERE tenant_id = %s
        """
        fc_params: list = [trunc, tenant_id]
        if product_id:
            fc_sql += " AND product_id = %s"
            fc_params.append(product_id)
        fc_sql += " GROUP BY 1 ORDER BY 1"
        cur.execute(fc_sql, fc_params)
        forecast = [
            {"date": d.isoformat(), "units": int(u), "kind": "forecast"} for d, u in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT f.product_id,
                   COALESCE(NULLIF(p.product_name, ''), f.product_id),
                   COALESCE(SUM(f.predicted_units), 0)::int AS u
            FROM forecasts f
            LEFT JOIN products p ON p.tenant_id = f.tenant_id AND p.product_id = f.product_id
            WHERE f.tenant_id = %s
            GROUP BY f.product_id, p.product_name
            ORDER BY u DESC LIMIT 10
            """,
            (tenant_id,),
        )
        top_products = [
            {"product_id": pid, "product_name": pname, "units": u} for pid, pname, u in cur.fetchall()
        ]

    # Série unifiée pour le graphique
    labels = sorted({h["date"] for h in history} | {f["date"] for f in forecast})
    hist_map = {h["date"]: h["units"] for h in history}
    fc_map = {f["date"]: f["units"] for f in forecast}
    series_history = [hist_map.get(d) for d in labels]
    series_forecast = [fc_map.get(d) for d in labels]

    return {
        "grain": grain,
        "labels": labels,
        "history_units": series_history,
        "forecast_units": series_forecast,
        "history": history,
        "forecast": forecast,
        "units": [fc_map.get(d, 0) for d in labels],  # compat ancien front
        "top_products": top_products,
    }


# --------------------------------------------------------------------------- auth register
class SellerRegister(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=120)
    contact_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=200)
    phone: str | None = Field(None, max_length=40)
    country: str | None = Field(None, max_length=80)


def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


@extra_router.post("/auth/register", tags=["auth"])
def register_seller(body: SellerRegister, conn=Depends(get_db)):
    email = body.email.strip().lower()
    if not _valid_email(email):
        raise HTTPException(400, "Email invalide")
    company = body.company_name.strip()
    contact = body.contact_name.strip()
    phone = (body.phone or "").strip() or None
    country = (body.country or "").strip() or None
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM tenants WHERE email = %s", (email,))
        if cur.fetchone():
            raise HTTPException(409, "Un compte existe déjà avec cet email")
        api_key = "df360_" + secrets.token_urlsafe(24)
        key_hash = hash_api_key(api_key)
        cur.execute(
            """
            INSERT INTO tenants (name, api_key_hash, email, company_name, contact_name, phone, country)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
            (company, key_hash, email, company, contact, phone, country),
        )
        tenant_id = str(cur.fetchone()[0])
    conn.commit()
    return {
        "tenant_id": tenant_id,
        "api_key": api_key,
        "company_name": company,
        "email": email,
        "message": "Conservez cette clé : elle ne sera plus affichée.",
    }


@extra_router.get("/auth/me", tags=["auth"])
def auth_me(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tenant_id, name, email, company_name, contact_name, phone, country
            FROM tenants WHERE tenant_id = %s
            """,
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


@extra_router.get("/kpi/by-category", tags=["kpi"])
def kpi_by_category(
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COALESCE(NULLIF(p.category, ''), 'Non classée') AS category,
                COUNT(*)::int AS units_sold,
                COALESCE(SUM(oi.item_total), 0)::float AS revenue,
                COALESCE(
                    SUM(COALESCE(p.product_cost, 0)),
                    0
                )::float AS cogs
            FROM order_items oi
            JOIN orders o
              ON o.tenant_id = oi.tenant_id
             AND o.order_id = oi.order_id
            LEFT JOIN products p
              ON p.tenant_id = oi.tenant_id
             AND p.product_id = oi.product_id
            WHERE oi.tenant_id = %s
              AND o.order_status != 'cancelled'
            GROUP BY COALESCE(NULLIF(p.category, ''), 'Non classée')
            ORDER BY revenue DESC
            """,
            (tenant_id,),
        )

        rows = cur.fetchall()

    categories = []

    for category, units_sold, revenue, cogs in rows:
        revenue = float(revenue or 0)
        cogs = float(cogs or 0)
        profit = revenue - cogs
        margin = round(100 * profit / revenue, 2) if revenue else 0

        categories.append(
            {
                "category": category,
                "units_sold": int(units_sold or 0),
                "revenue": round(revenue, 2),
                "cogs": round(cogs, 2),
                "profit": round(profit, 2),
                "margin": margin,
            }
        )

    return {"categories": categories}
