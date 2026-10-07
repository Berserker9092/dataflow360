# IMPORTS

import os
import joblib                        # sauvegarder / recharger le modèle
import numpy as np                   # calculs sur tableaux
import polars as pl                  # lecture rapide et préparation des données
import matplotlib.pyplot as plt      # graphiques

from sklearn.pipeline import Pipeline                       # enchaîne les étapes
from sklearn.compose import ColumnTransformer               # traitement par groupe de colonnes
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression         # modèle 1
from sklearn.ensemble import RandomForestClassifier         # modèle 2
from xgboost import XGBClassifier                           # modèle 3
from sklearn.metrics import (average_precision_score,       # PR-AUC
                             recall_score, precision_score,
                             precision_recall_curve,        # pour choisir le seuil
                             confusion_matrix,
                             ConfusionMatrixDisplay)


# CHARGEMENT (seules les colonnes utiles sont lues)
cols_events = ["order_id", "customer_id", "order_total_amount", "ip_country",
               "payment_method", "payment_source_country", "payment_status",
               "payment_attempt", "event_timestamp"]

events = pl.read_csv("checkout_events.csv", columns=cols_events, infer_schema_length=10000)
clients = pl.read_csv("customers.csv", columns=["customer_id", "country_code"], infer_schema_length=10000)
fraude = pl.read_csv("fraud.csv", columns=["order_id", "is_fraudulent"], infer_schema_length=10000)

# NETTOYAGE DES TYPES
# La date est lue comme du texte : on la convertit en vrai datetime
events = events.with_columns(
    pl.col("event_timestamp").str.to_datetime(strict=False)
)

# Le label doit être booléen (sinon on convertit "True"/"False")
if fraude.schema["is_fraudulent"] != pl.Boolean:
    fraude = fraude.with_columns(
        pl.col("is_fraudulent").cast(pl.String).str.to_lowercase() == "true"
    )

# UNE LIGNE PAR COMMANDE (dernière tentative de paiement)
# 51 490 événements pour 50 000 commandes : le label est par commande
last = (events.sort(["order_id", "payment_attempt"])
              .group_by("order_id", maintain_order=True).last())

# JOINTURES : pays du client + label de fraude
df = (last.join(clients, on="customer_id", how="left")
          .join(fraude, on="order_id", how="left"))

print(df.shape)                                                          # attendu : (50000, 11)
print(df["country_code"].null_count(), df["is_fraudulent"].null_count())  # attendu : 0 et 0
print(df["is_fraudulent"].mean())                                         # attendu : ~0.025


# CRÉATION DES FEATURES
df = df.with_columns([
    pl.col("order_total_amount").alias("amount_xof"),
    pl.col("event_timestamp").dt.hour().alias("hour_of_day"),
    (pl.col("event_timestamp").dt.weekday() - 1).alias("day_of_week"),            # 0 = lundi
    pl.col("payment_attempt").alias("payment_attempt_number"),
    pl.col("payment_source_country").fill_null("AUCUN"),                           # vide pour le cash
]).sort(["customer_id", "event_timestamp"])

# GÉOLOCALISATION : comparaison des 3 pays
# 1) normalisation (majuscules, sans espaces) pour éviter les faux écarts "sn" / "SN"
df = df.with_columns([
    pl.col("ip_country").str.to_uppercase().str.strip_chars().alias("ip_c"),                  # pays de l'IP
    pl.col("country_code").str.to_uppercase().str.strip_chars().alias("client_c"),            # pays du client
    pl.col("payment_source_country").str.to_uppercase().str.strip_chars()
      .fill_null("AUCUN").alias("card_c"),                                                    # pays de la carte / compte
])

# 2) comparaisons : 1 = pays différents, 0 = identiques
#    (pour le cash il n'y a pas de carte : les comparaisons avec la carte valent 0)
sans_carte = pl.col("card_c") == "AUCUN"
df = df.with_columns([
    (pl.col("ip_c") != pl.col("client_c")).fill_null(True).cast(pl.Int8).alias("geo_ip_client"),
    pl.when(sans_carte).then(pl.lit(0, dtype=pl.Int8))
      .otherwise((pl.col("card_c") != pl.col("client_c")).fill_null(True).cast(pl.Int8))
      .alias("geo_card_client"),
    pl.when(sans_carte).then(pl.lit(0, dtype=pl.Int8))
      .otherwise((pl.col("ip_c") != pl.col("card_c")).fill_null(True).cast(pl.Int8))
      .alias("geo_ip_card"),
])

# 3) total des désaccords (0 à 3) et statut pour le vendeur (il choisit : passer ou bloquer)
df = df.with_columns(
    (pl.col("geo_ip_client") + pl.col("geo_card_client") + pl.col("geo_ip_card"))
    .alias("geo_mismatch_count")
).with_columns(
    pl.when(pl.col("geo_mismatch_count") > 0)
      .then(pl.lit("ALERTE_VENDEUR"))
      .otherwise(pl.lit("OK"))
      .alias("geo_statut")
)
print(df["geo_statut"].value_counts())

# Vélocité : nombre de commandes du même client dans les 60 secondes précédentes
velocity = (
    df.rolling(index_column="event_timestamp", period="60s", group_by="customer_id")
      .agg(pl.col("order_id").count().alias("velocity_count_60s"))
      .unique(subset=["customer_id", "event_timestamp"], keep="first")
)
df = df.join(velocity, on=["customer_id", "event_timestamp"], how="left")
print(df.shape)   # doit rester à 50000 lignes : sinon la jointure a créé des doublons
print(df["velocity_count_60s"].value_counts().sort("velocity_count_60s"))


# COLONNES : numériques et catégorielles
NUM_FEATURES = ["amount_xof", "hour_of_day", "day_of_week", "velocity_count_60s",
                "geo_ip_client", "geo_card_client", "geo_ip_card", "geo_mismatch_count",
                "payment_attempt_number"]
CAT_FEATURES = ["payment_method", "ip_country", "payment_source_country", "payment_status"]
FEATURES = NUM_FEATURES + CAT_FEATURES

# Moyennes par classe : on voit déjà ce que le modèle va exploiter
print(df.group_by("is_fraudulent").agg(
    pl.col("velocity_count_60s").mean(),
    pl.col("geo_ip_client").mean(),
    pl.col("geo_card_client").mean(),
    pl.col("geo_ip_card").mean(),
    pl.col("geo_mismatch_count").mean(),
    pl.col("payment_attempt_number").mean(),
))


# SPLIT CHRONOLOGIQUE 70 / 15 / 15
df = df.sort("event_timestamp")
n = df.height
a, b = int(n * 0.70), int(n * 0.85)       # a = fin du train, b = fin de la validation
train, valid, test = df[:a], df[a:b], df[b:]

print("max train:", train["event_timestamp"].max(),
      "| min valid:", valid["event_timestamp"].min(),
      "| min test:", test["event_timestamp"].min())
print("fraudes train/valid/test:", train["is_fraudulent"].sum(),
      valid["is_fraudulent"].sum(), test["is_fraudulent"].sum())   # attendu : 880 / 201 / 169

# X = les features (tableau Polars, sans conversion), y = la réponse (0/1)
X_train = train.select(FEATURES)
X_valid = valid.select(FEATURES)
X_test = test.select(FEATURES)
y_train = train["is_fraudulent"].cast(pl.Int8).to_numpy()
y_valid = valid["is_fraudulent"].cast(pl.Int8).to_numpy()
y_test = test["is_fraudulent"].cast(pl.Int8).to_numpy()

# PIPELINES : encodage automatique + 3 modèles
def preparation(echelle):
    """One-hot sur le texte ; mise à l'échelle des nombres seulement si demandé."""
    nombres = StandardScaler() if echelle else "passthrough"
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT_FEATURES),
        ("num", nombres, NUM_FEATURES),
    ])

scale = (y_train == 0).sum() / (y_train == 1).sum()   # ~39 normales pour 1 fraude

modeles = {
    # Régression logistique : a besoin de nombres à la même échelle
    "logreg": Pipeline([
        ("prep", preparation(echelle=True)),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=1000)),
    ]),
    # Forêt aléatoire : 300 arbres qui votent, pas besoin de mise à l'échelle
    "random_forest": Pipeline([
        ("prep", preparation(echelle=False)),
        ("clf", RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                       class_weight="balanced_subsample",
                                       n_jobs=-1, random_state=42)),
    ]),
    # XGBoost : arbres construits l'un après l'autre
    "xgboost": Pipeline([
        ("prep", preparation(echelle=False)),
        ("clf", XGBClassifier(scale_pos_weight=scale, random_state=42)),
    ]),
}

# =====================================================
# ÉVALUATION : PR-AUC pour comparer, seuil choisi sur la validation
# =====================================================
def meilleur_seuil(y_vrai, proba):
    """Seuil de probabilité qui donne le meilleur équilibre précision / recall (F1)."""
    prec, rap, seuils = precision_recall_curve(y_vrai, proba)
    f1 = 2 * prec[:-1] * rap[:-1] / (prec[:-1] + rap[:-1] + 1e-9)
    return seuils[np.argmax(f1)]

print("PR-AUC d'un modèle au hasard :", round(float(y_test.mean()), 4))   # = le taux de fraude

lignes, probas_test, seuils_modeles = [], {}, {}
for nom, pipe in modeles.items():
    pipe.fit(X_train, y_train)                              # 1. apprentissage (train)
    p_valid = pipe.predict_proba(X_valid)[:, 1]             # 2. scores sur la validation
    seuil = float(meilleur_seuil(y_valid, p_valid))         # 3. seuil choisi sur la validation
    p_test = pipe.predict_proba(X_test)[:, 1]               # 4. évaluation finale (test)
    preds = (p_test >= seuil).astype(int)
    probas_test[nom] = p_test
    seuils_modeles[nom] = seuil
    lignes.append({
        "modele": nom,
        "PR-AUC valid": float(average_precision_score(y_valid, p_valid)),
        "seuil": seuil,
        "PR-AUC test": float(average_precision_score(y_test, p_test)),
        "recall test": float(recall_score(y_test, preds)),
        "precision test": float(precision_score(y_test, preds, zero_division=0)),
    })

res = pl.DataFrame(lignes)
with pl.Config(tbl_cols=-1, tbl_width_chars=200):
    print(res.with_columns(pl.col(pl.Float64).round(3)))

# Le modèle gagnant est choisi sur la VALIDATION, jamais sur le test
meilleur = res.sort("PR-AUC valid", descending=True)["modele"][0]
print("modèle choisi :", meilleur)
pipe, seuil = modeles[meilleur], seuils_modeles[meilleur]
preds_final = (probas_test[meilleur] >= seuil).astype(int)
cm = confusion_matrix(y_test, preds_final)
print(cm)

affichage = ConfusionMatrixDisplay(
    confusion_matrix=cm,
    display_labels=["Normale", "Fraude"],
)
affichage.plot(cmap="Blues", values_format="d")
plt.title(f"Matrice de confusion ({meilleur}, seuil = {seuil:.3f})")
plt.xlabel("Prédiction du modèle")
plt.ylabel("Réalité")
plt.tight_layout()
plt.show()

# Courbes précision-recall des trois modèles
for nom, p in probas_test.items():
    prec, rap, _ = precision_recall_curve(y_test, p)
    auc = res.filter(pl.col("modele") == nom)["PR-AUC test"][0]
    plt.plot(rap, prec, label=f"{nom} ({auc:.3f})")
plt.axhline(y_test.mean(), ls="--", c="grey", label="hasard")
plt.xlabel("Recall")
plt.ylabel("Precision")
plt.title("Courbes précision-recall (test)")
plt.legend()
plt.show()

# IMPORTANCE DES VARIABLES (du modèle choisi)
noms = pipe.named_steps["prep"].get_feature_names_out()
clf = pipe.named_steps["clf"]
# régression logistique : poids (coef_) ; arbres : feature_importances_
valeurs = np.abs(clf.coef_[0]) if hasattr(clf, "coef_") else clf.feature_importances_
ordre = np.argsort(valeurs)[-10:]                 # les 10 plus importantes
plt.barh(noms[ordre], valeurs[ordre])
plt.title(f"Importance des variables ({meilleur})")
plt.tight_layout()
plt.show()

# SAUVEGARDE (pipeline + features + seuil)
os.makedirs("models", exist_ok=True)
joblib.dump({"pipeline": pipe, "features": FEATURES,
             "threshold": float(seuil), "model_name": meilleur},
            "models/fraud_model.pkl")

# PRÉDICTION TEMPS RÉEL (modèle chargé une seule fois)
ART = joblib.load("models/fraud_model.pkl")

def predict_fraud(features: dict):
    """Reçoit un dict avec les 13 features ; renvoie (probabilité, est_fraude)."""
    X = pl.DataFrame([features]).select(ART["features"])
    proba = float(ART["pipeline"].predict_proba(X)[0, 1])
    return proba, proba >= ART["threshold"]