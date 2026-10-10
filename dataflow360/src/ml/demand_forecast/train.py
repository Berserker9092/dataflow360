"""
DataFlow360 - Prévision HEBDOMADAIRE de la demande PAR PRODUIT : ENTRAÎNEMENT.

Ce fichier entraîne le modèle et le sauvegarde dans models/forecast_<tenant>.pkl.
Les prévisions sont produites par predict.py (même organisation que fraud_detection : train.py / scoring.py).

Source : le data warehouse PostgreSQL de l'équipe (tables tenants, orders, order_items, products),
comme prévu à l'étape 58 du guide. Un mode CSV reste disponible pour tester sans base.

Usage (depuis la racine du code, base démarrée et remplie par l'ETL) :
    python -m src.ml.demand_forecast.train --host localhost --port 5433 --password ...
    python -m src.ml.demand_forecast.train --fast                 # plus rapide (moins d'arbres)
    python -m src.ml.demand_forecast.train --no-backtest          # ré-entraînement seul (job de nuit)
    python -m src.ml.demand_forecast.train --data-dir data/raw    # mode CSV (hors base)

Ré-entraînement depuis un autre module (ex. src/batch/nightly_jobs.py, étape 43 du guide) :
    from src.ml.demand_forecast.train import retrain
    retrain(tenant="tenant_demo")        # sans backtest, écrit models/forecast_tenant_demo.pkl

Méthode
- Série = unités vendues par produit et par semaine (lundi -> dimanche), semaines
  complètes seulement, semaines sans vente = 0.
- UN seul modèle global pour tous les produits (un modèle par produit n'aurait
  presque aucune donnée : la demande est très intermittente), avec une perte de
  Poisson adaptée aux comptages (beaucoup de 0, quelques 1, 2, 3...).
- Prévision DIRECTE multi-horizon : un modèle par horizon h = 1..H semaines.
  Les features sont calculées à la fin de la semaine t, la cible est la demande
  de la semaine t+h. Pas de prévision récursive, donc pas d'accumulation d'erreur.
- Backtest honnête : les N dernières semaines servent de test ; les baselines sont
  "toujours 0", "moyenne historique du produit" et "moyenne des 13 dernières semaines".
"""
import argparse
import os
import pathlib

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

FEATURES = [
    "cat_code", "log_price",
    "lag0", "lag1", "lag2", "lag3",
    "sum4", "sum13", "sum26",
    "rate_all", "weeks_since_sale", "cum_units", "n_sale_weeks_26",
    "target_woy", "target_month",
]
MIN_T = 26      # première semaine d'origine utilisable (besoin de 26 semaines d'historique)
NEVER = 200     # "semaines depuis la dernière vente" pour un produit jamais vendu


# ------------------------------------------------------------------ données
EXCLUDED_STATUSES = ("cancelled", "canceled", "failed")


def connect_db(a):
    """Connexion PostgreSQL : par défaut get_pg_connection() du dépôt (même configuration que l'équipe) ;
    sinon connexion explicite (--host/--port/--db/--user/--password ou variables POSTGRES_*)."""
    if a.host is None:
        try:
            from src.storage.db_connection import get_pg_connection

            return get_pg_connection()
        except Exception as exc:  # module absent, .env absent, base arrêtée...
            print(f"[info] get_pg_connection() inutilisable ({exc}) -> connexion explicite sur localhost")
    params = dict(host=a.host or "localhost", port=a.port, dbname=a.db, user=a.user, password=a.password)
    try:
        try:
            import psycopg

            return psycopg.connect(**params)
        except ImportError:
            import psycopg2

            return psycopg2.connect(**params)
    except Exception as exc:
        raise SystemExit(f"Connexion PostgreSQL impossible sur {params['host']}:{params['port']} ({exc}).\n"
                         f"Vérifie que le conteneur postgres tourne (docker compose ps), le port (5432 dans le compose du dépôt, "
                         f"5433 chez Ousmane) et le mot de passe (--port / --password).") from None


def _db_columns(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s AND table_schema = current_schema()", (table,))
    return {r[0] for r in cur.fetchall()}


def _read_db(a, statuses):
    """Lit les ventes hebdomadaires dans le data warehouse PostgreSQL (source prévue par le guide, étape 58)."""
    conn = connect_db(a)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id::text FROM tenants WHERE name = %s", (a.tenant,))
            row = cur.fetchone()
            if row is None:
                cur.execute("SELECT name FROM tenants ORDER BY name")
                known = ", ".join(r[0] for r in cur.fetchall()) or "aucun"
                raise SystemExit(f"Tenant '{a.tenant}' introuvable dans la table tenants (existants : {known}). "
                                 f"Crée-le puis lance l'ETL, ou passe --tenant <nom>.")
            tenant_id = row[0]

            oi_cols, p_cols = _db_columns(cur, "order_items"), _db_columns(cur, "products")
            if "quantity" in oi_cols:
                qty = "SUM(oi.quantity)"
            else:
                qty = "COUNT(*)"
                print("[attention] pas de colonne quantity dans order_items : unités = nombre de lignes de commande")
            if statuses == "all":
                cond, st_params = "o.order_status NOT IN ('cancelled', 'canceled', 'failed')", ()
            else:
                lst = statuses.split(",")
                cond, st_params = "o.order_status IN (" + ", ".join(["%s"] * len(lst)) + ")", tuple(lst)
            params = (tenant_id,) + st_params

            cur.execute(f"SELECT MIN(o.order_purchase_timestamp), MAX(o.order_purchase_timestamp) FROM orders o "
                        f"WHERE o.tenant_id = %s::uuid AND {cond} AND o.order_purchase_timestamp IS NOT NULL", params)
            tmin, tmax = cur.fetchone()
            if tmin is None:
                raise SystemExit(f"Aucune commande pour le tenant '{a.tenant}' (statuts : {statuses}) : "
                                 f"la base est-elle remplie (ETL lancé) ?")
            cur.execute(
                f"SELECT oi.product_id, DATE_TRUNC('week', o.order_purchase_timestamp)::date AS week, {qty} AS units "
                f"FROM order_items oi JOIN orders o ON o.tenant_id = oi.tenant_id AND o.order_id = oi.order_id "
                f"WHERE oi.tenant_id = %s::uuid AND {cond} AND o.order_purchase_timestamp IS NOT NULL "
                f"GROUP BY 1, 2", params)
            agg = pd.DataFrame(cur.fetchall(), columns=["product_id", "week", "quantity"])

            cols = ["product_id"] + [c for c in ("category", "price", "product_cost", "stock_quantity") if c in p_cols]
            cur.execute(f"SELECT {', '.join(cols)} FROM products WHERE tenant_id = %s::uuid", (tenant_id,))
            products = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()

    agg["week"] = pd.to_datetime(agg["week"])
    agg["quantity"] = pd.to_numeric(agg["quantity"]).astype(float)
    for c in ("price", "product_cost", "stock_quantity"):
        if c in products:
            products[c] = pd.to_numeric(products[c], errors="coerce")
    if "price" not in products and "product_cost" in products:
        print("[info] le warehouse ne contient pas le prix de vente : le coût d'achat (product_cost) sert de proxy de prix")
        products["price"] = products["product_cost"]
    return products.drop_duplicates("product_id").reset_index(drop=True), agg, pd.Timestamp(tmin), pd.Timestamp(tmax)


def _read_csv(data_dir, statuses):
    """Lit les CSV bruts (mode hors base, pour tester sans Docker). Mêmes règles de nettoyage que l'ETL."""
    d = pathlib.Path(data_dir)
    orders = pd.read_csv(d / "orders.csv", usecols=["order_id", "order_status", "order_purchase_timestamp"])
    items = pd.read_csv(d / "order_items.csv", usecols=["order_id", "order_item_id", "product_id", "quantity"])
    products = pd.read_csv(d / "products.csv")

    orders = orders.drop_duplicates("order_id")
    items = items.drop_duplicates(["order_id", "order_item_id"])
    products = products.rename(columns={"category_name": "category"})
    keep = ["product_id"] + [c for c in ("category", "price", "stock_quantity") if c in products.columns]
    products = products[keep].drop_duplicates("product_id").reset_index(drop=True)

    if statuses == "all":
        orders = orders[~orders["order_status"].isin(EXCLUDED_STATUSES)]
    else:
        orders = orders[orders["order_status"].isin(statuses.split(","))]
    # utc=True puis tz_localize(None) : gère aussi les dates ISO avec fuseau (ex. 2024-01-01T10:00:00+00:00)
    ts = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce", utc=True).dt.tz_localize(None)
    orders = orders.assign(ts=ts).dropna(subset=["ts"])
    if orders.empty:
        raise SystemExit("Aucune commande exploitable : vérifie --statuses et le format de order_purchase_timestamp.")
    orders["week"] = orders["ts"].dt.to_period("W-SUN").dt.start_time
    m = items.merge(orders[["order_id", "week"]], on="order_id", how="inner")
    agg = m.groupby(["product_id", "week"], as_index=False)["quantity"].sum()
    return products, agg, orders["ts"].min(), orders["ts"].max()


def load_weekly(a):
    if a.source == "db":
        products, agg, tmin, tmax = _read_db(a, a.statuses)
    else:
        products, agg, tmin, tmax = _read_csv(a.data_dir, a.statuses)

    # semaines COMPLÈTES uniquement (lundi -> dimanche) : la 1re et la dernière sont souvent partielles
    tmin, tmax = tmin.normalize(), tmax.normalize()
    first = tmin if tmin.dayofweek == 0 else tmin + pd.Timedelta(days=7 - tmin.dayofweek)
    last_sunday = tmax if tmax.dayofweek == 6 else tmax - pd.Timedelta(days=tmax.dayofweek + 1)
    weeks = pd.date_range(first, last_sunday - pd.Timedelta(days=6), freq="7D")

    pidx = pd.Index(products["product_id"])
    pi, wi = pidx.get_indexer(agg["product_id"]), weeks.get_indexer(agg["week"])
    n_unknown = int((pi < 0).sum())
    if n_unknown:
        print(f"[attention] {n_unknown} lignes avec un produit absent de la table produits : ignorées")
    ok = (pi >= 0) & (wi >= 0)
    U = np.zeros((len(products), len(weeks)), dtype=np.float32)
    U[pi[ok], wi[ok]] = agg["quantity"].to_numpy()[ok]
    if not U.any():
        raise SystemExit("Aucune vente rattachée aux produits : vérifie que product_id est identique dans "
                         "les commandes et les produits, et que les dates tombent dans des semaines complètes.")

    cat = products["category"] if "category" in products else pd.Series("na", index=products.index)
    price = products["price"].fillna(0).to_numpy(dtype=np.float32) if "price" in products else np.ones(len(products), np.float32)
    return products, U, weeks, np.log1p(price), cat.to_numpy()


def encode_categories(cat, levels=None):
    """Code numérique des catégories. À l'entraînement (levels=None) on mémorise l'ordre des catégories ;
    à la prédiction on réutilise exactement les mêmes codes que ceux appris (catégorie inconnue = -1)."""
    if levels is None:
        codes, uniques = pd.factorize(pd.Series(cat))
        return codes.astype(np.float32), [str(u) for u in uniques]
    m = {c: i for i, c in enumerate(levels)}
    return np.array([m.get(str(c), -1) for c in cat], dtype=np.float32), list(levels)


# ------------------------------------------------------------------ features
def build_features(U, cat_code, log_price, weeks_ext, t_idx, h):
    """Une ligne par (produit, origine t). Utilise UNIQUEMENT les semaines <= t."""
    P, W = U.shape
    cs = np.concatenate([np.zeros((P, 1), np.float32), np.cumsum(U, axis=1, dtype=np.float32)], axis=1)
    sc = np.concatenate([np.zeros((P, 1), np.float32), np.cumsum(U > 0, axis=1, dtype=np.float32)], axis=1)
    last = np.maximum.accumulate(np.where(U > 0, np.arange(W)[None, :], -1), axis=1)

    blocks, ys = [], []
    for t in t_idx:
        win = lambda k: cs[:, t + 1] - cs[:, max(t + 1 - k, 0)]
        ws = np.where(last[:, t] >= 0, t - last[:, t], NEVER).astype(np.float32)
        tw = weeks_ext[t + h]
        blocks.append(np.column_stack([
            cat_code, log_price,
            U[:, t], U[:, t - 1], U[:, t - 2], U[:, t - 3],
            win(4), win(13), win(26),
            cs[:, t + 1] / (t + 1), ws, cs[:, t + 1],
            sc[:, t + 1] - sc[:, max(t + 1 - 26, 0)],
            np.full(P, tw.isocalendar().week, np.float32), np.full(P, tw.month, np.float32),
        ]))
        ys.append(U[:, t + h] if t + h < W else np.full(P, np.nan, np.float32))
    X = pd.DataFrame(np.vstack(blocks), columns=FEATURES)
    return X, np.concatenate(ys), np.tile(np.arange(P), len(t_idx)), np.repeat(np.asarray(t_idx), P)


def new_model(trees=300, lr=0.05):
    return XGBRegressor(
        objective="count:poisson", n_estimators=trees, max_depth=5, learning_rate=lr,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
        tree_method="hist", random_state=42, n_jobs=-1,
    )


def wape(y, p):
    return float(np.abs(y - p).sum() / max(float(y.sum()), 1e-9))


def rmse(y, p):
    return float(np.sqrt(np.mean((y - p) ** 2)))


def poisson_dev(y, p, eps=1e-3):
    """Déviance de Poisson moyenne : métrique propre pour des comptages creux.
    (Le WAPE/MAE est trompeur ici : avec ~94 % de zéros, prévoir 0 partout minimise l'erreur absolue.)"""
    p = np.clip(p, eps, None)
    term = np.where(y > 0, y * np.log(np.where(y > 0, y, 1.0) / p), 0.0)
    return float(2.0 * np.mean(term - (y - p)))


# ------------------------------------------------------------------ pipeline
def main(a):
    products, U, weeks, log_price, cat = load_weekly(a)
    cat_code, cat_levels = encode_categories(cat)
    P, W = U.shape
    H = a.horizon
    print(f"{P} produits, {W} semaines complètes ({weeks[0].date()} -> {weeks[-1].date()}), "
          f"{int(U.sum())} unités, source = {a.source}, statuts = {a.statuses}")
    print(f"Demande moyenne : {U.mean():.3f} unité / produit / semaine ; "
          f"{(U == 0).mean():.1%} des produit-semaines sont à 0")
    nz = int((U.sum(axis=1) > 0).sum())
    print(f"Produits vendus au moins une fois : {nz}/{P}")

    test_w = a.test_weeks
    if W < MIN_T + test_w + H + 20:
        test_w = max(W - MIN_T - H - 20, 0)
        print(f"[attention] historique court : backtest réduit à {test_w} semaines")
    weeks_ext = weeks.append(pd.date_range(weeks[-1] + pd.Timedelta(days=7), periods=H, freq="7D"))
    cutoff = W - test_w  # premières semaines-cibles du test

    # ---------------- backtest
    if test_w >= 4 and not a.no_backtest:
        print(f"\n=== BACKTEST : {test_w} dernières semaines, prévision à 1..{H} semaines ===")
        rows = []
        t0 = cutoff - 1  # origine unique pour le classement : aucune info du test dans les features
        rk = {k: np.zeros(P) for k in ("p", "b", "r", "y")}
        n_rank = 0
        for h in range(1, H + 1):
            Xtr, ytr, _, _ = build_features(U, cat_code, log_price, weeks_ext, range(cutoff - 1 - h, MIN_T - 1, -a.stride), h)
            Xte, yte, pte, tte = build_features(U, cat_code, log_price, weeks_ext, range(cutoff - h, W - h), h)
            model = new_model(a.trees, a.lr).fit(Xtr, ytr)
            p = np.clip(model.predict(Xte), 0, None)
            base = {"zero": np.zeros_like(p), "moy. historique": Xte["rate_all"].to_numpy(),
                    "moy. 13 sem.": Xte["sum13"].to_numpy() / 13}
            allp = {**base, "modèle": p}
            r = {"h": h, **{f"rmse|{k}": rmse(yte, v) for k, v in allp.items()},
                 **{f"mae|{k}": float(np.abs(yte - v).mean()) for k, v in allp.items()},
                 **{f"dev|{k}": poisson_dev(yte, v) for k, v in allp.items() if k != "zero"},
                 "biais": float(p.sum() / max(yte.sum(), 1e-9) - 1)}
            df = pd.DataFrame({"cat": cat[pte], "wk": tte + h, "y": yte, "p": p, "b": base["moy. 13 sem."]})
            g = df.groupby(["cat", "wk"])[["y", "p", "b"]].sum()
            r["agrégé modèle"], r["agrégé moy13"] = wape(g["y"].to_numpy(), g["p"].to_numpy()), wape(g["y"].to_numpy(), g["b"].to_numpy())
            rows.append(r)
            if t0 + h < W:  # la semaine cible t0+h est dans le test
                X0, _, _, _ = build_features(U, cat_code, log_price, weeks_ext, [t0], h)
                rk["p"] += np.clip(model.predict(X0), 0, None)
                rk["b"] += X0["sum13"].to_numpy() / 13
                rk["r"] += X0["rate_all"].to_numpy()
                rk["y"] += U[:, t0 + h]
                n_rank += 1
        res = pd.DataFrame(rows).set_index("h")
        names = ["zero", "moy. historique", "moy. 13 sem.", "modèle"]
        print("RMSE par produit-semaine (plus bas = mieux) :")
        print(res[[f"rmse|{n}" for n in names]].set_axis(names, axis=1).round(4).to_string())
        print("\nMAE par produit-semaine (critère littéral de l'étape 60 du guide ; trompeur ici : avec ~94 % de zéros, "
              "prévoir 0 minimise la MAE) :")
        print(res[[f"mae|{n}" for n in names]].set_axis(names, axis=1).round(4).to_string())
        ok_mae = bool((res["mae|modèle"] < res["mae|moy. 13 sem."]).all())
        print(f"Critère du guide (MAE modèle < MAE moyenne mobile, ici la moyenne sur 13 semaines) : "
              f"{'RESPECTÉ' if ok_mae else 'NON RESPECTÉ'}")
        print("\nDéviance de Poisson (plus bas = mieux ; adaptée aux comptages avec beaucoup de zéros) :")
        print(res[[f"dev|{n}" for n in names[1:]]].set_axis(names[1:], axis=1).round(4).to_string())
        best_dev = res[["dev|moy. historique", "dev|moy. 13 sem."]].min(axis=1)
        best_rmse = res[["rmse|moy. historique", "rmse|moy. 13 sem."]].min(axis=1)
        print("\nGain du modèle vs la meilleure baseline :  "
              + ", ".join(f"h{h}: RMSE {1 - res.loc[h, 'rmse|modèle'] / best_rmse[h]:+.1%} / déviance {1 - res.loc[h, 'dev|modèle'] / best_dev[h]:+.1%}"
                          for h in res.index))
        print(f"Biais (somme prédite / somme réelle - 1) : "
              f"{', '.join(f'h{h}={v:+.1%}' for h, v in res['biais'].items())}")
        print("\nWAPE agrégé par catégorie et par semaine (somme sur les produits ; cette échelle est lisible) :")
        print((res[["agrégé modèle", "agrégé moy13"]] * 100).round(1).astype(str).add(" %").to_string())
        k = max(int(0.05 * P), 1)
        top = {n: float(rk["y"][np.argsort(-rk[c])[:k]].sum() / max(rk["y"].sum(), 1e-9))
               for n, c in [("modèle", "p"), ("moy. 13 sem.", "b"), ("moy. historique", "r")]}
        print(f"\nClassement des produits : à partir de la dernière semaine avant le test (origine unique), part de la "
              f"demande réelle des {n_rank} semaines suivantes captée par les 5 % de produits les mieux classés "
              f"(5 % = hasard) : " + ", ".join(f"{n}={v:.1%}" for n, v in top.items()))
        g_rmse = float((1 - res["rmse|modèle"] / best_rmse).mean())
        g_dev = float((1 - res["dev|modèle"] / best_dev).mean())
        g = min(g_rmse, g_dev)  # on juge sur le plus faible des deux gains
        if g < 0:
            verdict = "est MOINS BON que"
        elif g < 0.01:
            verdict = "est ÉQUIVALENT à (gain < 1 %)"
        elif g < 0.05:
            verdict = "est LÉGÈREMENT meilleur que"
        else:
            verdict = "est NETTEMENT meilleur que"
        print(f"-> Gain moyen vs meilleure baseline : RMSE {g_rmse:+.1%}, déviance {g_dev:+.1%}. "
              f"Le modèle {verdict} la meilleure baseline.")

    # ---------------- entraînement final sur tout l'historique + sauvegarde
    print(f"\n=== ENTRAÎNEMENT FINAL sur tout l'historique ({W} semaines, horizons 1..{H}) ===")
    models = {}
    for h in range(1, H + 1):
        Xtr, ytr, _, _ = build_features(U, cat_code, log_price, weeks_ext, range(W - 1 - h, MIN_T - 1, -a.stride), h)
        models[h] = new_model(a.trees, a.lr).fit(Xtr, ytr)
    mdir = pathlib.Path(a.out_dir)
    mdir.mkdir(parents=True, exist_ok=True)
    path = mdir / f"forecast_{a.tenant}.pkl"
    joblib.dump({"models": models, "features": FEATURES, "cat_levels": cat_levels, "horizon": H,
                 "last_week": str(weeks[-1].date()), "tenant": a.tenant}, path)
    print(f"Modèle sauvegardé : {path}")
    print("Pour produire les prévisions : python -m src.ml.demand_forecast.predict (mêmes options de connexion)")
    return path


# ------------------------------------------------------------------ options (partagées avec predict.py)
def add_data_args(ap):
    ap.add_argument("--source", choices=["db", "csv"], default=None,
                    help="db = PostgreSQL (data warehouse, source prévue par le guide) ; csv = fichiers bruts. "
                         "Par défaut : csv si --data-dir est donné, sinon db")
    ap.add_argument("--data-dir", default=None, help="dossier des CSV (mode csv)")
    ap.add_argument("--host", default=None, help="PostgreSQL : si absent, utilise get_pg_connection() du dépôt")
    ap.add_argument("--port", default=os.getenv("POSTGRES_PORT", "5432"))
    ap.add_argument("--db", default=os.getenv("POSTGRES_DB", "dataflow360"))
    ap.add_argument("--user", default=os.getenv("POSTGRES_USER", "dataflow"))
    ap.add_argument("--password", default=os.getenv("POSTGRES_PASSWORD", ""))
    ap.add_argument("--statuses", default="all", help="'all' = tout sauf annulées/échouées, ou ex. delivered,shipped")
    ap.add_argument("--tenant", default="tenant_demo", help="nom du tenant (modèle : forecast_<tenant>.pkl)")
    ap.add_argument("--out-dir", default="models", help="dossier du modèle")
    ap.add_argument("--processed-dir", default="data/processed", help="dossier des fichiers de prévision (predict.py)")


def finalize_args(args):
    if args.source is None:
        args.source = "csv" if args.data_dir else "db"
    if args.source == "csv" and not args.data_dir:
        args.data_dir = "data/raw"
    if getattr(args, "fast", False):
        args.trees, args.lr, args.stride = 100, 0.12, 2
    return args


def build_parser():
    ap = argparse.ArgumentParser(description="Entraîne le modèle de prévision hebdomadaire par produit.")
    add_data_args(ap)
    ap.add_argument("--horizon", type=int, default=4, help="nombre de semaines à prévoir")
    ap.add_argument("--test-weeks", type=int, default=13)
    ap.add_argument("--trees", type=int, default=300, help="nombre d'arbres (moins = plus rapide)")
    ap.add_argument("--lr", type=float, default=0.05, help="learning rate")
    ap.add_argument("--stride", type=int, default=1, help="n'utilise qu'1 semaine d'origine sur N pour entraîner (2 = 2x plus rapide)")
    ap.add_argument("--fast", action="store_true", help="raccourci : --trees 100 --lr 0.12 --stride 2")
    ap.add_argument("--no-backtest", action="store_true", help="ré-entraîne seulement (pas de comparaison aux baselines) : pour un job de nuit")
    return ap


def retrain(tenant="tenant_demo", **options):
    """Ré-entraînement sans backtest, appelable depuis un job planifié (étape 43 du guide).
    Les options sont celles de la ligne de commande, avec _ au lieu de - (ex. host="localhost", port=5433)."""
    a = build_parser().parse_args([])
    a.tenant, a.no_backtest = tenant, True
    for k, v in options.items():
        if not hasattr(a, k):
            raise TypeError(f"option inconnue : {k}")
        setattr(a, k, v)
    return main(finalize_args(a))


if __name__ == "__main__":
    main(finalize_args(build_parser().parse_args()))