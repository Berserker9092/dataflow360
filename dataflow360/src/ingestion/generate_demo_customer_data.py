"""Génère des noms clients réalistes (Afrique de l'Ouest) pour le dashboard démo."""

from __future__ import annotations

import random

from src.storage.db_connection import get_pg_connection
from src.ingestion.elt_pipeline import get_tenant_uuid


FIRST = [
    "Aminata", "Awa", "Fatou", "Mariama", "Khady", "Aissatou", "Ndeye", "Adama",
    "Ibrahima", "Moussa", "Ousmane", "Cheikh", "Mamadou", "Abdoulaye", "Modou",
    "Seydou", "Kofi", "Kwame", "Ama", "Akosua", "Yao", "Fatimata", "Boubacar",
]

LAST = [
    "Diallo", "Traoré", "Ouattara", "Koné", "Coulibaly", "Sow", "Ndiaye", "Fall",
    "Sarr", "Ba", "Camara", "Keita", "Touré", "Sangaré", "Diop", "Gueye", "Cissé",
]


def main() -> None:
    conn = get_pg_connection()
    tenant_id = get_tenant_uuid()
    rng = random.Random(42)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT customer_id, city, country
            FROM customers
            WHERE tenant_id = %s
              AND (full_name IS NULL OR full_name = '')
            """,
            (tenant_id,),
        )

        rows = cur.fetchall()

        for i, (cid, city, country) in enumerate(rows):
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            email = (
                f"{name.lower().replace(' ', '.')}"
                f"{i % 1000}@example.com"
            )

            cur.execute(
                """
                UPDATE customers
                SET full_name = %s,
                    email = COALESCE(email, %s)
                WHERE tenant_id = %s
                  AND customer_id = %s
                """,
                (name, email, tenant_id, cid),
            )

            if (i + 1) % 2000 == 0:
                conn.commit()
                print(f"  {i + 1}/{len(rows)}")

    conn.commit()
    print(f"OK : {len(rows)} clients nommés (tenant {tenant_id})")


if __name__ == "__main__":
    main()
