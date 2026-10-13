"""Insère les prévisions (CSV) dans la table forecasts de PostgreSQL."""

import os
from pathlib import Path

import polars as pl

from src.storage.db_connection import get_pg_connection


def main():
    tenant_name = os.getenv("TENANT_NAME", "Boutique démo")
    csv_path = Path("data/processed/forecast_products_weekly.csv")

    if not csv_path.exists():
        print(f"❌ Fichier introuvable : {csv_path}")
        return

    # 1. Résoudre le tenant_id (UUID)
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM tenants WHERE name = %s",
                (tenant_name,),
            )
            row = cur.fetchone()
            if not row:
                print(f"❌ Tenant introuvable : {tenant_name}")
                return
            tenant_id = str(row[0])
    finally:
        conn.close()

    print(f"Tenant : {tenant_name} ({tenant_id})")

    # 2. Lire le CSV
    df = pl.read_csv(csv_path)
    print(f"CSV : {len(df)} lignes lues")

    # 3. Nettoyer : supprimer l'ancienne version
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM forecasts WHERE tenant_id = %s",
                (tenant_id,),
            )
            print(f"  Anciennes prévisions supprimées")

            # 4. Insérer
            rows = []
            for r in df.iter_rows(named=True):
                predicted = max(0, int(round(r["predicted_units"])))
                rows.append((
                    tenant_id,
                    r["product_id"],
                    r["week_start"],
                    predicted,
                ))

            cur.executemany(
                """
                INSERT INTO forecasts (tenant_id, product_id, forecast_date, predicted_units)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, product_id, forecast_date)
                DO UPDATE SET predicted_units = EXCLUDED.predicted_units
                """,
                rows,
            )
        conn.commit()
        print(f"✅ {len(rows)} prévisions insérées")
    except Exception as e:
        conn.rollback()
        print(f"❌ Erreur : {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
