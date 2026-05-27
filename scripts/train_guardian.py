"""Train the Guardian binary classifier on cycles_detected.

Label:    pre-fee profitability (raw_log_return > 0)
Features: venue (one-hot), direction (binary), hour-of-day + day-of-week
          (cyclical sin/cos), and rolling statistics.

The label captures whether a triangular mispricing exists at all (before
fees consume it). The features are limited to information that is
available at detection time and NOT directly used in computing the label,
which avoids data leakage.

Outputs:
    models/guardian_v1.joblib           — trained model + calibrator + threshold
    reports/guardian_metrics.json       — AUC, precision, recall
    reports/guardian_pr_curve.png       — precision-recall curve
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR  = REPO_ROOT / "models"
REPORTS_DIR = REPO_ROOT / "reports"
MODELS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://localhost:5432/omniarb"
)


def load_cycles() -> pd.DataFrame:
    """Pull cycles_detected into a DataFrame, parse legs JSON, build features."""
    with psycopg2.connect(DATABASE_URL) as conn:
        df = pd.read_sql(
            """
            SELECT
              id, ts, venue, legs,
              raw_log_return, expected_return,
              passed_profit, rejection_reason
            FROM cycles_detected
            ORDER BY ts ASC, id ASC
            """,
            conn,
        )
    df["legs"]      = df["legs"].apply(lambda v: v if isinstance(v, dict) else json.loads(v))
    df["direction"] = df["legs"].apply(lambda d: d.get("direction", ""))
    df["is_fwd"]    = (df["direction"].str.contains("BTC->ETH")).astype(int)
    df["ts"]        = pd.to_datetime(df["ts"], utc=True)
    df["label"]     = (df["raw_log_return"].astype(float) > 0).astype(int)
    return df


def build_features(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Construct an X matrix using only LEAKAGE-FREE inputs."""
    venues = ["binance", "bybit", "coinbase", "kraken"]
    cols: list[np.ndarray] = []
    names: list[str] = []

    # Venue one-hot
    for v in venues:
        cols.append((df["venue"] == v).astype(int).to_numpy())
        names.append(f"venue_{v}")

    # Direction
    cols.append(df["is_fwd"].to_numpy())
    names.append("is_fwd")

    # Cyclical time encoding
    secs = df["ts"].dt.hour * 3600 + df["ts"].dt.minute * 60 + df["ts"].dt.second
    tod = 2 * math.pi * secs / 86400.0
    dow = 2 * math.pi * df["ts"].dt.weekday / 7.0
    cols += [np.sin(tod), np.cos(tod), np.sin(dow), np.cos(dow)]
    names += ["tod_sin", "tod_cos", "dow_sin", "dow_cos"]

    # Per-venue rolling positive-rate (50-cycle window) as a momentum feature
    df_sorted = df.sort_values(["venue", "ts"])
    rolling = (
        df_sorted.groupby("venue")["label"]
        .rolling(window=50, min_periods=10)
        .mean()
        .shift(1)  # critical: shift so we don't leak the current label
        .reset_index(level=0, drop=True)
        .fillna(0.0)
        .reindex(df.index)
        .to_numpy()
    )
    cols.append(rolling)
    names.append("rolling_pos_rate_50")

    X = np.column_stack(cols).astype(float)
    return X, names


def walk_forward_split(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """70 / 15 / 15 chronological split."""
    train_end = int(n * 0.70)
    val_end   = int(n * 0.85)
    idx = np.arange(n)
    return idx[:train_end], idx[train_end:val_end], idx[val_end:]


def main() -> int:
    print(f"Loading cycles from {DATABASE_URL}...")
    df = load_cycles()
    print(f"Loaded {len(df):,} cycles  ({df['label'].sum():,} positive, "
          f"{df['label'].mean()*100:.2f}%)")

    if df["label"].sum() < 50:
        print("ERROR: fewer than 50 positive examples — can't train meaningfully.")
        return 1

    X, feature_names = build_features(df)
    y = df["label"].to_numpy()

    train_idx, val_idx, test_idx = walk_forward_split(len(y))
    print(f"Splits — train: {len(train_idx):,}  val: {len(val_idx):,}  test: {len(test_idx):,}")
    print(f"        train_pos: {y[train_idx].mean():.3f}  "
          f"val_pos: {y[val_idx].mean():.3f}  "
          f"test_pos: {y[test_idx].mean():.3f}")

    print("\nTraining LightGBM...")
    clf = lgb.LGBMClassifier(
        objective="binary", n_estimators=300, learning_rate=0.05,
        max_depth=6, num_leaves=31, min_child_samples=20,
        random_state=42, verbose=-1,
    )
    clf.fit(X[train_idx], y[train_idx])

    raw_val  = clf.predict_proba(X[val_idx])[:, 1]
    raw_test = clf.predict_proba(X[test_idx])[:, 1]

    print("Calibrating with isotonic regression on validation set...")
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw_val, y[val_idx])
    cal_test = iso.transform(raw_test)

    auc      = float(roc_auc_score(y[test_idx], cal_test))
    avg_prec = float(average_precision_score(y[test_idx], cal_test))

    # Pick threshold on validation set that maximises F1
    p, r, t = precision_recall_curve(y[val_idx], iso.transform(raw_val))
    f1 = 2 * p * r / np.maximum(p + r, 1e-9)
    best = int(np.argmax(f1[:-1])) if len(f1) > 1 else 0
    threshold = float(t[best]) if len(t) > 0 else 0.5

    pred = (cal_test >= threshold).astype(int)
    tp = int(((pred == 1) & (y[test_idx] == 1)).sum())
    test_precision = tp / max(int(pred.sum()), 1)
    test_recall    = tp / max(int(y[test_idx].sum()), 1)

    print("\n" + "=" * 60)
    print(f"Test AUC (calibrated)      : {auc:.4f}")
    print(f"Test Avg Precision         : {avg_prec:.4f}")
    print(f"Chosen threshold (val F1)  : {threshold:.4f}")
    print(f"Test precision @ threshold : {test_precision:.4f}")
    print(f"Test recall    @ threshold : {test_recall:.4f}")
    print("=" * 60)

    # Feature importances
    print("\nFeature importances (gain):")
    importances = sorted(
        zip(feature_names, clf.booster_.feature_importance(importance_type="gain")),
        key=lambda kv: -kv[1],
    )
    for name, gain in importances:
        print(f"  {name:30s}  {gain:>12,.1f}")

    # Persist bundle
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    artifact_path = MODELS_DIR / f"guardian_v1_{stamp}.joblib"
    joblib.dump(
        {
            "model":        clf,
            "calibrator":   iso,
            "threshold":    threshold,
            "feature_order": feature_names,
            "test_metrics": {
                "auc": auc, "avg_precision": avg_prec,
                "precision": test_precision, "recall": test_recall,
            },
        },
        artifact_path,
    )
    print(f"\nSaved artifact: {artifact_path}")

    # Metrics JSON
    metrics_path = REPORTS_DIR / "guardian_metrics.json"
    metrics_path.write_text(json.dumps({
        "test_auc":         auc,
        "test_avg_precision": avg_prec,
        "test_precision":   test_precision,
        "test_recall":      test_recall,
        "threshold":        threshold,
        "n_train":          len(train_idx),
        "n_val":            len(val_idx),
        "n_test":           len(test_idx),
        "feature_importances": dict(importances),
    }, indent=2))
    print(f"Saved metrics : {metrics_path}")

    # PR curve plot
    p_test, r_test, _ = precision_recall_curve(y[test_idx], cal_test)
    plt.figure(figsize=(7, 5))
    plt.plot(r_test, p_test, color="#FF8C42", linewidth=2)
    plt.axhline(y[test_idx].mean(), linestyle="--", color="grey",
                label=f"Random baseline = {y[test_idx].mean():.2f}")
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title(f"Guardian PR curve — AUC={auc:.3f}, AP={avg_prec:.3f}")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    pr_path = REPORTS_DIR / "guardian_pr_curve.png"
    plt.savefig(pr_path, dpi=150)
    print(f"Saved PR curve: {pr_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
