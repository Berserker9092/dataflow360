"""Endpoints additionnels pour le dashboard Vue complet (sans modifier routes.py).

Dans src/api/main.py, après include_router(router) :
    from src.api.routes_extra import extra_router
    app.include_router(extra_router)
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.api.deps import get_current_tenant, get_db
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
    """Liste paginée pour la page Commandes du frontend Vue."""
    sort_col = {
        "date": "o.order_purchase_timestamp",
        "status": "o.order_status",
        "amount": "o.order_total_amount",
    }.get(sort, "o.order_purchase_timestamp")
    order_dir = "ASC" if dir.lower() == "asc" else "DESC"

    where = ["o.tenant_id = %s"]
    params: list = [tenant_id]
    if status and status != "all":
        # frontend envoie canceled ; schéma utilise souvent cancelled
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
        where.append("(o.order_id ILIKE %s OR o.customer_id ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])

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
        items = []
        for oid, ts, cid, st, amount, nitems in cur.fetchall():
            status_out = "canceled" if st == "cancelled" else (st or "")
            items.append(
                {
                    "order_id": oid,
                    "date": ts.isoformat() if ts else None,
                    "customer_id": cid,
                    "status": status_out,
                    "items": int(nitems),
                    "amount": int(amount or 0),
                }
            )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@extra_router.get("/orders/export", tags=["orders"])
def export_orders(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    status: str = "all",
    tenant_id: str = Depends(get_current_tenant),
    conn=Depends(get_db),
):
    data = list_orders(
        from_=from_,
        to=to,
        status=status,
        q="",
        sort="date",
        dir="desc",
        page=1,
        page_size=100,
        tenant_id=tenant_id,
        conn=conn,
    )
    # export élargi (plusieurs pages max 500)
    all_items = list(data["items"])
    total = data["total"]
    page = 2
    while len(all_items) < min(total, 500):
        chunk = list_orders(
            from_=from_,
            to=to,
            status=status,
            page=page,
            page_size=100,
            tenant_id=tenant_id,
            conn=conn,
        )
        if not chunk["items"]:
            break
        all_items.extend(chunk["items"])
        page += 1

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order_id", "date", "customer_id", "status", "items", "amount"])
    for r in all_items:
        w.writerow([r["order_id"], r["date"], r["customer_id"], r["status"], r["items"], r["amount"]])
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
    """Feed temps réel pour la page Live (poll 3 s)."""
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
            (now - timedelta(minutes=5), now - timedelta(minutes=5),
             now - timedelta(minutes=60), now - timedelta(minutes=60), tenant_id),
        )
        o5, r5, o60, r60 = cur.fetchone()

        # série par minute (30 min)
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
        by_min = {row[0].replace(tzinfo=None) if hasattr(row[0], "replace") else row[0]: int(row[1]) for row in cur.fetchall()}
        series = []
        for i in range(29, -1, -1):
            m = (now - timedelta(minutes=i)).replace(second=0, microsecond=0)
            # match approx minute keys
            cnt = 0
            for k, v in by_min.items():
                if isinstance(k, datetime) and abs((k - m).total_seconds()) < 30:
                    cnt = v
                    break
            series.append({"minutes_ago": i, "orders": cnt})

        cur.execute(
            """
            SELECT order_id, order_purchase_timestamp, order_total_amount, order_status, customer_id
            FROM orders
            WHERE tenant_id = %s
            ORDER BY order_purchase_timestamp DESC NULLS LAST
            LIMIT %s
            """,
            (tenant_id, limit),
        )
        events = []
        for oid, ts, amount, st, cid in cur.fetchall():
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
                }
            )

    pending = 0
    try:
        pending = get_redis().hlen(f"fraud_alerts:{tenant_id}") or 0
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
        "pending_alerts": int(pending),
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
            "SELECT city, country FROM customers WHERE tenant_id = %s AND customer_id = %s",
            (tenant_id, customer_id),
        )
        row = cur.fetchone()
        if not row:
            # client peut n'exister que via orders
            cur.execute(
                "SELECT 1 FROM orders WHERE tenant_id = %s AND customer_id = %s LIMIT 1",
                (tenant_id, customer_id),
            )
            if not cur.fetchone():
                raise HTTPException(404, "Client introuvable")
            city, country = None, None
        else:
            city, country = row

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
            SELECT TO_CHAR(DATE_TRUNC('month', order_purchase_timestamp), 'YYYY-MM') AS m,
                   COALESCE(SUM(order_total_amount), 0)
            FROM orders
            WHERE tenant_id = %s AND customer_id = %s AND order_status != 'cancelled'
            GROUP BY 1 ORDER BY 1
            """,
            (tenant_id, customer_id),
        )
        monthly_rows = cur.fetchall()
        monthly = {
            "labels": [r[0] for r in monthly_rows],
            "revenue": [int(r[1]) for r in monthly_rows],
        }

        cur.execute(
            """
            SELECT oi.product_id, COALESCE(SUM(oi.item_total), 0) AS rev
            FROM order_items oi
            JOIN orders o USING (tenant_id, order_id)
            WHERE o.tenant_id = %s AND o.customer_id = %s AND o.order_status != 'cancelled'
            GROUP BY oi.product_id ORDER BY rev DESC LIMIT 10
            """,
            (tenant_id, customer_id),
        )
        products = [{"product_id": p, "revenue": int(r)} for p, r in cur.fetchall()]

        cur.execute(
            """
            SELECT order_id, order_purchase_timestamp, order_status, order_total_amount
            FROM orders
            WHERE tenant_id = %s AND customer_id = %s
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
        "city": city,
        "country": country,
        "orders": int(n or 0),
        "lifetime_value": int(spent or 0),
        "aov": float(aov or 0),
        "first_order": first.isoformat() if first else None,
        "last_order": last.isoformat() if last else None,
        "monthly": monthly,
        "products": products,
        "orders_list": orders_list,
    }


# --------------------------------------------------------------------------- reports forecast
@extra_router.get("/reports/forecast", tags=["forecast"])
def report_forecast(tenant_id: str = Depends(get_current_tenant), conn=Depends(get_db)):
    """Agrégat journalier des prévisions (page Forecast overview)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT forecast_date, COALESCE(SUM(predicted_units), 0)
            FROM forecasts
            WHERE tenant_id = %s
            GROUP BY forecast_date ORDER BY forecast_date
            """,
            (tenant_id,),
        )
        rows = cur.fetchall()
        cur.execute(
            """
            SELECT product_id, COALESCE(SUM(predicted_units), 0) AS u
            FROM forecasts WHERE tenant_id = %s
            GROUP BY product_id ORDER BY u DESC LIMIT 10
            """,
            (tenant_id,),
        )
        top = [{"product_id": p, "units": int(u)} for p, u in cur.fetchall()]
    return {
        "labels": [d.isoformat() if hasattr(d, "isoformat") else str(d) for d, _ in rows],
        "units": [int(u) for _, u in rows],
        "top_products": top,
    }
