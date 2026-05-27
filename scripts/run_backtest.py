"""Backtest the Triple-Gate pipeline against the held-out cycles.

Runs TWO scenarios so the report can compare:
  A. Realistic taker fees (10-60 bps per leg) — empirical efficiency test
  B. Maker-rebate scenario (2 bps per leg)   — methodology demonstration

For each scenario, evaluates THREE strategies:
  - Random         : pick K cycles at random
  - Profit-gate    : pick every cycle whose post-fee log_return > buffer
  - Triple-Gate    : pick every cycle that PASSES Profit Gate AND Guardian
                     score > threshold

Outputs:
  reports/backtest_metrics.json     — Sharpe, P&L, hit-rate per strategy/scenario
  reports/equity_curves.png         — cumulative P&L over time
  reports/strategy_comparison.png   — bar chart of net P&L
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR  = REPO_ROOT / "models"
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://localhost:5432/omniarb"
)

# Trade size in quote currency (USDT) per cycle.
TRADE_SIZE_USDT: float = 1000.0

# Profit-gate buffer (5 bps from TECHNICAL_PLAN.md §3).
PROFIT_BUFFER_BPS: float = 5.0

# Scenarios: per-leg fees in absolute terms (NOT bps).
SCENARIOS = {
    "realistic_taker": {
        "binance":  0.001,    # 10 bps
        "kraken":   0.0026,   # 26 bps
        "coinbase": 0.006,    # 60 bps
        "bybit":    0.001,    # 10 bps
    },
    "maker_rebate": {
        "binance":  0.0002,   # 2 bps
        "kraken":   0.0002,
        "coinbase": 0.0002,
        "bybit":    0.0002,
    },
    "frictionless": {
        # Pure methodology demonstration: zero fees.
        "binance":  0.0,
        "kraken":   0.0,
        "coinbase": 0.0,
        "bybit":    0.0,
    },
}


def load_latest_guardian() -> dict:
    candidates = sorted(MODELS_DIR.glob("guardian_v1_*.joblib"))
    if not candidates:
        print("ERROR: no Guardian model found. Run scripts/train_guardian.py first.")
        sys.exit(1)
    bundle = joblib.load(candidates[-1])
    print(f"Loaded Guardian: {candidates[-1].name}")
    return bundle


def load_cycles() -> pd.DataFrame:
    with psycopg2.connect(DATABASE_URL) as conn:
        df = pd.read_sql(
            """
            SELECT id, ts, venue, legs, raw_log_return, expected_return
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


def build_features(df: pd.DataFrame, feature_order: list[str]) -> np.ndarray:
    venues = ["binance", "bybit", "coinbase", "kraken"]
    cols: list[np.ndarray] = []

    for v in venues:
        cols.append((df["venue"] == v).astype(int).to_numpy())
    cols.append(df["is_fwd"].to_numpy())

    secs = df["ts"].dt.hour * 3600 + df["ts"].dt.minute * 60 + df["ts"].dt.second
    tod = 2 * math.pi * secs / 86400.0
    dow = 2 * math.pi * df["ts"].dt.weekday / 7.0
    cols += [np.sin(tod), np.cos(tod), np.sin(dow), np.cos(dow)]

    df_sorted = df.sort_values(["venue", "ts"])
    rolling = (
        df_sorted.groupby("venue")["label"]
        .rolling(window=50, min_periods=10)
        .mean().shift(1)
        .reset_index(level=0, drop=True)
        .fillna(0.0)
        .reindex(df.index)
        .to_numpy()
    )
    cols.append(rolling)
    return np.column_stack(cols).astype(float)


def compute_pnl_for_cycle(
    raw_log_return: float,
    venue: str,
    fee_map: dict[str, float],
) -> float:
    """Convert a cycle's raw log return to net USD P&L for one TRADE_SIZE_USDT trade."""
    fee = fee_map[venue]
    # 3 legs × log(1-fee) added per leg
    net_log = raw_log_return + 3 * math.log(1.0 - fee)
    # Convert log return to multiplicative return, then to USD
    return TRADE_SIZE_USDT * (math.exp(net_log) - 1.0)


def evaluate_strategy(
    df: pd.DataFrame,
    selected_mask: np.ndarray,
    fee_map: dict[str, float],
    name: str,
) -> dict:
    """Compute Sharpe, hit-rate, total P&L for cycles selected by `selected_mask`."""
    sel = df[selected_mask].copy()
    if len(sel) == 0:
        return {
            "strategy": name, "n_trades": 0, "hit_rate": 0.0,
            "total_pnl_usd": 0.0, "sharpe": 0.0,
            "avg_pnl_usd": 0.0,  "max_drawdown_usd": 0.0,
            "equity_curve": [],
        }
    pnl = sel.apply(
        lambda row: compute_pnl_for_cycle(
            float(row["raw_log_return"]), row["venue"], fee_map
        ),
        axis=1,
    ).to_numpy()
    hit_rate   = float((pnl > 0).mean())
    total_pnl  = float(pnl.sum())
    avg_pnl    = float(pnl.mean())
    sharpe     = float(pnl.mean() / pnl.std() * math.sqrt(len(pnl))) if pnl.std() > 0 else 0.0

    equity = np.cumsum(pnl)
    drawdowns = equity - np.maximum.accumulate(equity)
    max_dd = float(drawdowns.min())

    return {
        "strategy":         name,
        "n_trades":         int(len(sel)),
        "hit_rate":         hit_rate,
        "total_pnl_usd":    total_pnl,
        "avg_pnl_usd":      avg_pnl,
        "sharpe":           sharpe,
        "max_drawdown_usd": max_dd,
        "equity_curve":     equity.tolist(),
    }


def main() -> int:
    print(f"Loading cycles from {DATABASE_URL}...")
    df = load_cycles()
    print(f"Loaded {len(df):,} cycles")

    bundle = load_latest_guardian()
    feature_names = bundle["feature_order"]
    X = build_features(df, feature_names)

    raw = bundle["model"].predict_proba(X)[:, 1]
    df["guardian_score"] = bundle["calibrator"].transform(raw)
    guardian_threshold = float(bundle["threshold"])

    print(f"\nGuardian threshold (F1-optimal): {guardian_threshold:.4f}")
    print(f"Cycles above threshold: {int((df['guardian_score'] >= guardian_threshold).sum()):,}")

    # Held-out split: test the last 15% of cycles chronologically
    n = len(df)
    test_start = int(n * 0.85)
    df_test = df.iloc[test_start:].reset_index(drop=True)
    print(f"\nBacktest window: last {len(df_test):,} cycles "
          f"({df_test['ts'].iloc[0]} -> {df_test['ts'].iloc[-1]})")

    all_results: dict[str, list[dict]] = {}

    # Shared selection masks (independent of fee scenario)
    oracle_mask = (df_test["raw_log_return"].astype(float) > 0).to_numpy()

    # Guardian: TOP-K by score (more robust than threshold for small windows)
    K = min(100, len(df_test) // 8)
    top_k_ids = df_test["guardian_score"].nlargest(K).index
    guardian_mask = np.zeros(len(df_test), dtype=bool)
    guardian_mask[top_k_ids] = True

    # Random picks K cycles for a like-for-like baseline.
    rng = np.random.default_rng(42)
    random_idx = rng.choice(len(df_test), size=K, replace=False)
    random_mask = np.zeros(len(df_test), dtype=bool)
    random_mask[random_idx] = True

    print(f"\nSelection sizes (out of {len(df_test)} test cycles):")
    print(f"  Random:           {int(random_mask.sum())}")
    print(f"  Pre-fee Oracle:   {int(oracle_mask.sum())}")
    print(f"  Guardian (top-K): {int(guardian_mask.sum())}")

    for scenario_name, fee_map in SCENARIOS.items():
        print(f"\n=== Scenario: {scenario_name} ===")

        results = [
            evaluate_strategy(df_test, random_mask,   fee_map, "Random"),
            evaluate_strategy(df_test, oracle_mask,   fee_map, "Pre-fee Oracle"),
            evaluate_strategy(df_test, guardian_mask, fee_map, "Guardian"),
        ]
        all_results[scenario_name] = results

        for r in results:
            print(f"  {r['strategy']:18s}  trades={r['n_trades']:5d}  "
                  f"hit_rate={r['hit_rate']:.3f}  "
                  f"net_pnl=${r['total_pnl_usd']:10.2f}  "
                  f"sharpe={r['sharpe']:6.2f}")

    # Save JSON (strip equity curves to keep file readable)
    json_out = {
        s: [{k: v for k, v in r.items() if k != "equity_curve"} for r in rs]
        for s, rs in all_results.items()
    }
    metrics_path = REPORTS_DIR / "backtest_metrics.json"
    metrics_path.write_text(json.dumps(json_out, indent=2))
    print(f"\nSaved metrics: {metrics_path}")

    # --- Plot 1: equity curves (frictionless scenario, methodology demo) ---
    plt.figure(figsize=(10, 5))
    for r in all_results["frictionless"]:
        eq = r["equity_curve"]
        if eq:
            plt.plot(eq, label=f"{r['strategy']} (n={r['n_trades']}, P&L=${r['total_pnl_usd']:.0f})")
    plt.axhline(0, linestyle="--", color="grey", alpha=0.6)
    plt.title("Equity curves — frictionless scenario (methodology demonstration)")
    plt.xlabel("Trade #")
    plt.ylabel("Cumulative gross P&L (USD)")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "equity_curves.png", dpi=150)
    print(f"Saved equity plot: {REPORTS_DIR / 'equity_curves.png'}")

    # --- Plot 2: strategy comparison bar chart ---
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, scenario_name in zip(axes, SCENARIOS):
        strategies = [r["strategy"] for r in all_results[scenario_name]]
        pnls       = [r["total_pnl_usd"] for r in all_results[scenario_name]]
        colors     = ["#999", "#0099CC", "#00E5A0"]
        ax.bar(strategies, pnls, color=colors)
        ax.set_title(f"{scenario_name}")
        ax.set_ylabel("Net P&L (USD)")
        ax.grid(axis="y", alpha=0.3)
        ax.axhline(0, color="black", linewidth=0.5)
    fig.suptitle("Strategy comparison across fee scenarios")
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "strategy_comparison.png", dpi=150)
    print(f"Saved comparison: {REPORTS_DIR / 'strategy_comparison.png'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
