"""
DataFlow360 - Prévision de la demande par produit : UTILISATION du modèle entraîné par train.py
(même organisation que fraud_detection : train.py entraîne, ce fichier sert).

Il lit les ventes dans PostgreSQL (ou les CSV), charge models/forecast_<tenant>.pkl et prévoit,
pour chaque produit, la demande (en unités) des H prochaines semaines.

Usage (depuis la racine du code) :
    python -m src.ml.demand_forecast.predict --host localhost --port 5433 --password ...

Depuis un autre module (backend, dashboard, job planifié) :
    from src.ml.demand_forecast.predict import get_forecast
    forecast, summary = get_forecast(tenant="tenant_demo", host="localhost", port=5433, password="...")

Sorties : data/processed/forecast_products_weekly.csv (1 ligne par produit et semaine) et
data/processed/forecast_products_summary.csv (total sur H semaines + couverture de stock).
"""
import argparse
import pathlib

import joblib
import numpy as np
import pandas as pd

from .train import FEATURES, add_data_args, build_features, encode_categories, finalize_args, load_weekly


def load_model(tenant, model_dir="models"):
    path = pathlib.Path(model_dir) / f"forecast_{tenant}.pkl"
    if not path.exists():
        raise SystemExit(f"Modèle introuvable : {path}. Entraîne-le d'abord : "
                         f"python -m src.ml.demand_forecast.train --tenant {tenant}")
    art = joblib.load(path)
    if art["features"] != FEATURES:
        raise SystemExit("Ce modèle a été entraîné avec d'autres variables que le code actuel : relance train.py.")
    return art


def forecast_from_model(art, products, U, weeks, log_price, cat, tenant):
    """Prévision des art['horizon'] prochaines semaines, à partir de la dernière semaine complète des données."""
    models, H = art["models"], art["horizon"]
    P, W = U.shape
    cat_code, _ = encode_categories(cat, art["cat_levels"])
    weeks_ext = weeks.append(pd.date_range(weeks[-1] + pd.Timedelta(days=7), periods=H, freq="7D"))
    out = []
    for h in range(1, H + 1):
        Xnow, _, pn, _ = build_features(U, cat_code, log_price, weeks_ext, [W - 1], h)
        p = np.clip(models[h].predict(Xnow), 0, None)
        out.append(pd.DataFrame({"product_id": products["product_id"].to_numpy()[pn], "category": cat[pn],
                                 "week_start": weeks_ext[W - 1 + h].date(), "horizon": h,
                                 "predicted_units": p.round(3)}))
    fc = pd.concat(out, ignore_index=True)
    fc.insert(0, "tenant_id", tenant)

    tot = fc.groupby("product_id")["predicted_units"].sum()
    summ = products.assign(**{f"predicted_{H}w": products["product_id"].map(tot).to_numpy(),
                              "sold_last_26w": U[:, -26:].sum(axis=1)})
    if "stock_quantity" in summ:
        weekly = (summ[f"predicted_{H}w"] / H).replace(0, np.nan)
        summ["weeks_of_cover"] = (summ["stock_quantity"] / weekly).round(1)
    return fc, summ.sort_values(f"predicted_{H}w", ascending=False)


def _run(a):
    art = load_model(a.tenant, a.out_dir)
    products, U, weeks, log_price, cat = load_weekly(a)
    if str(weeks[-1].date()) != art["last_week"]:
        print(f"[info] modèle entraîné jusqu'à la semaine du {art['last_week']}, données jusqu'à celle du "
              f"{weeks[-1].date()} : les features utilisent les données actuelles, relance train.py pour ré-entraîner.")
    fc, summ = forecast_from_model(art, products, U, weeks, log_price, cat, a.tenant)
    return art, weeks, fc, summ


def get_forecast(tenant="tenant_demo", **options):
    """Renvoie (prévisions par produit et semaine, résumé par produit). Options = celles de la ligne de commande."""
    ap = argparse.ArgumentParser()
    add_data_args(ap)
    a = ap.parse_args([])
    a.tenant = tenant
    for k, v in options.items():
        if not hasattr(a, k):
            raise TypeError(f"option inconnue : {k}")
        setattr(a, k, v)
    _, _, fc, summ = _run(finalize_args(a))
    return fc, summ


def main(a):
    art, weeks, fc, summ = _run(a)
    H = art["horizon"]
    proc = pathlib.Path(a.processed_dir)
    proc.mkdir(parents=True, exist_ok=True)
    fc.to_csv(proc / "forecast_products_weekly.csv", index=False)
    summ.to_csv(proc / "forecast_products_summary.csv", index=False)

    print(f"=== PRÉVISION : {H} semaines à partir de la semaine du {weeks[-1].date()} (tenant {a.tenant}) ===")
    print("Demande prévue par catégorie (unités par semaine) :")
    print(fc.groupby(["category", "horizon"])["predicted_units"].sum().unstack().round(0).to_string())
    print(f"\nFichiers : {proc}/forecast_products_weekly.csv (1 ligne par produit et semaine), "
          f"{proc}/forecast_products_summary.csv (total {H} sem. + couverture de stock)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Prévision hebdomadaire de la demande par produit (modèle déjà entraîné).")
    add_data_args(ap)
    main(finalize_args(ap.parse_args()))