# Project Omni-Arb v2.0 — Technical Plan

**Course:** USI · Master in Finance Y1 · Programming in Finance & Economics II
**Authors:** Andrea Cammarano, Giacomo Lanni, Edoardo Praderio (+ AI Associate)
**Status:** v2.0 — supersedes the v1 slides dated April 2026
**Repository:** https://github.com/edoardopraderio23/CRYPTO-ARBITRAGE-TRADING-BOT

---

## 0. Summary of changes vs v1

This plan tightens nine specific weaknesses identified in the v1 slide deck. Each section below addresses one weakness, states the v1 position, the v2 commitment, and how it will be verified.

| # | Topic | v1 position | v2 commitment |
|---|---|---|---|
| 1 | Latency target | "<10 ms detection-to-execution" | Measured budget, p50 ≈ 19 ms, p95 ≈ 32 ms |
| 2 | Economic premise | Implicit | Explicit market-efficiency thesis with a falsifiable question |
| 3 | Profit gate | None | Fee-aware filter rejects ~92% of raw cycles before ML |
| 4 | ML labeling rule | Undefined | Replay-based binary label, 5 bps band |
| 5 | ML model | Random Forest only | LightGBM primary + RF interpretable baseline |
| 6 | Risk / inventory | Not mentioned | Sentinel component: leg-failure protocol, inventory cap, drawdown halt |
| 7 | Architecture name | "Triple-Check" (3 components, not 3 checks) | "Triple-Gate" (3 actual rejection filters) |
| 8 | Backtest design | "Paper trading" only | Walk-forward, fee-aware fill model, calibration metrics |
| 9 | Third generic criterion | Unspecified | PostgreSQL with 4 core tables (locks rubric coverage at 3/3) |

The rest of this document elaborates each.

---

## 1. Latency: replace the unrealistic <10 ms claim

### Why it had to change

CCXT (and CCXT Pro) is a Python wrapper over exchange WebSocket APIs. Empirically, JSON parse + book reconstruction alone consumes 5–10 ms on a modest VPS. Adding graph rebuild and ML inference makes the original "<10 ms" target impossible without rewriting in C++ and colocating — neither of which is in scope for a four-week academic project.

Worse, putting an unverifiable number on a slide invites the professor to ask "show me." We replace it with a measured budget.

### New latency budget (target, will be benchmarked)

| Stage | Median | p95 | Notes |
|---|---|---|---|
| WebSocket ingestion + parse | 8 ms | 12 ms | CCXT Pro, single-thread asyncio |
| Graph build + Bellman-Ford | 6 ms | 11 ms | Incremental update on edge changes only |
| Profit Gate (analytic) | <1 ms | 2 ms | Pure arithmetic; no I/O |
| Confidence Gate (LightGBM) | 3 ms | 6 ms | ~30 features, ~200 trees |
| Risk Gate (table lookup) | <1 ms | 1 ms | In-memory inventory cache |
| **End-to-end (signal logged)** | **≈ 19 ms** | **≈ 32 ms** | Excludes network RTT to exchange |

### How we verify

The Scout writes `t_received` per book event. Each downstream component logs `t_in` and `t_out`. CI emits a latency-budget report per build; a regression of >20% on p95 fails the build.

---

## 2. Economic premise: state it, defend it, falsify it

### v2 thesis (one paragraph for the report)

> Crypto triangular arbitrage at retail latency in 2026 is dominated by HFT firms with sub-millisecond colocated infrastructure. After taker fees of ~10 bps per leg (≈ 30 bps round-trip), the median raw negative-cycle signal observed on Binance/Kraken/Coinbase is unprofitable. Our hypothesis is that the residual edge — if any — lies not in detecting cycles faster, but in *selecting* which cycles will execute as priced. We test this hypothesis by constructing a three-gate filtering system and measuring whether the gated subset of cycles produces positive post-fee P&L on out-of-sample data. A negative result is itself an academically valuable measurement of market efficiency.

### What this buys us with the grader

1. The "real-life viability" objection is preempted: we explicitly *expect* the strategy to be marginal or unprofitable, and frame the project as a market-efficiency study.
2. The hypothesis is falsifiable: post-fee Sharpe on holdout < 0 ⇒ thesis rejected, but the *selection* metric (precision-at-threshold) is still reportable.
3. Lessons-learned section (rubric: "include a Lessons Learned section") writes itself from the falsification analysis.

---

## 3. Profit Gate (NEW component)

### Specification

For each detected negative cycle `(c1, c2, c3)` on a venue, compute:

```
expected_return = ln(rate(c1, c2) * rate(c2, c3) * rate(c3, c1))
fees            = ln(1 - fee_taker) * 3       # symmetric across 3 legs
slippage_buffer = 5e-4                         # 5 bps default, tunable per pair

PASS ⇔ expected_return  >  -fees + slippage_buffer
```

### Why this matters

The ML model in v1 was being asked to learn fee economics from labels. That conflates two distinct decisions: "is this cycle priced profitably?" (deterministic, math) and "will this cycle execute as priced?" (stochastic, ML). Separating them:
- removes the dominant source of label noise from the training set,
- makes the ML problem learnable with the small datasets we can collect in 3 weeks,
- gives us interpretable rejection reasons in the post-mortem ("rejected: post-fee", "rejected: low p̂").

### Empirical anchor

In a 14-day Binance pilot replay over BTC-ETH-USDT we expect ~92% of detected cycles to be rejected at this gate. The exact figure goes into the report.

---

## 4. ML labeling rule (was undefined in v1)

### The hard problem

We are not actually executing trades, so there are no real fill outcomes to label with. Three candidate labeling strategies were evaluated:

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| (a) Use historical execution data | Ground truth | We don't have it | Reject |
| (b) Replay against next-tick book | Reproducible, defensible | Approximation of real fill | **Adopt** |
| (c) Self-supervised: predict next-second mid-price | No label needed | Not what the system actually needs | Reject |

### The chosen rule

For each cycle the Brain emits at time `t`, we replay it against the order book at `t + Δ` (Δ = 50 ms, the realistic order placement delay). We simulate aggressive (taker) fills against displayed depth, leg by leg. The label is:

```
y = 1  ⇔  realized_post_fee_return  ≥  expected_return − 5 bps  for all 3 legs
y = 0  otherwise
```

### Features (initial set — will be pruned via SHAP)

1. `spread_top` — top-of-book spread on each leg
2. `depth5_imbalance` — sum of bid_size_5 / sum of ask_size_5
3. `queue_size_top` — bid_size_1, ask_size_1
4. `vol_5s`, `vol_30s` — realized volatility on each leg's mid
5. `inter_book_latency_ms` — server-side ping log delta
6. `time_of_day`, `day_of_week` — cyclical encoding
7. `last_trade_dir` — +1 / −1, last 100 ms
8. `recent_fill_ratio` — fraction of last 100 displayed depth that actually traded

### Class imbalance handling

Expected positive rate ≈ 30–50% after the Profit Gate. If imbalance >70/30, apply class weights (not SMOTE, to preserve calibration).

---

## 5. ML model: LightGBM primary, Random Forest interpretable baseline

### Why we changed from RF-only

| Criterion | Random Forest | LightGBM |
|---|---|---|
| Tabular performance | Good | Almost always better on financial features |
| Inference latency | ~6 ms (200 trees) | ~3 ms (200 trees, histogram split) |
| Native handling of NaN | Requires imputation | Built-in |
| Probability calibration | Tends to over-confidence | Same; both need calibration |
| Interpretability | High (feature importance via mean-decrease-impurity is robust) | Slightly lower |

### Final design

- **LightGBM** is the production scoring model. Trained with `objective=binary`, `metric=auc`, calibrated post-hoc with isotonic regression on the validation fold.
- **Random Forest** trains on the same features and labels. It serves three purposes:
  1. Acts as an interpretable baseline (for the report's feature analysis).
  2. Provides a sanity-check on LightGBM scores (large divergence flags overfitting).
  3. Anchors the rubric's "machine learning model" advanced criterion with a textbook implementation graders can follow without external knowledge.

### Decision threshold

Trade fires only if `calibrated_p̂ > 0.85`. The threshold is **chosen on the validation set** to maximize precision subject to recall ≥ 0.30, **not** on the holdout.

### Reported metrics

- Precision-at-threshold (primary)
- Recall, F1, AUC (secondary)
- Reliability diagram (calibration plot in the LaTeX report)
- Post-fee paper Sharpe of the gated trade set on holdout

---

## 6. Sentinel: risk and inventory (NEW component)

### Why a strategy without failure-mode modeling is incomplete

Triangular arbitrage is multi-leg. If leg 2 of 3 fails, the bot is left holding an unwanted currency. v1 said nothing about this. In the worst case the strategy looks profitable until the first failure cluster, then bleeds inventory loss for hours.

### v2 controls

#### 6.1 Leg-failure protocol
On every leg-failure event:
1. Sentinel emits a `contingency_unwind` order: market-out at prevailing bid/ask.
2. The event is logged to `trades_simulated` with a `failure_unwind` flag and the realized loss.
3. Each event becomes a labeled negative example for v2 of the Guardian (closed feedback loop).

#### 6.2 Inventory cap
- Hard cap: `max(|exposure_per_currency|) ≤ $X` (default $1,000 in paper trading).
- New cycles whose leg 1 would push any non-base currency past the cap are rejected at the Risk Gate, before the Profit Gate even runs (latency-cheap rejection first).

#### 6.3 Drawdown halt
- Trading auto-pauses if rolling 24-h paper P&L < `μ − 2σ` of expected.
- Resumption requires an explicit human ack via the agentic workflow (see `AGENTS.md`).
- This protects against silent feature drift in the ML model.

---

## 7. Triple-Gate, not Triple-Check

The v1 slide named three *components* (Scout, Brain, Guardian) and called the system "Triple-Check." But Scout doesn't check anything — it streams. The naming was misleading.

v2 retains the three components but elevates three *gates* to first-class architectural concept. The pipeline is:

```
            ┌───────────┐
WebSocket ─►│   SCOUT   │  (data + persistence)
            └─────┬─────┘
                  ▼
            ┌───────────┐
            │   BRAIN   │  (cycle detection)
            └─────┬─────┘
                  ▼
              [GATE 1: PROFIT]   ── reject if ROI ≤ fees + buffer
                  ▼
            ┌───────────┐
            │  GUARDIAN │  (ML scoring)
            └─────┬─────┘
                  ▼
              [GATE 2: CONFIDENCE]   ── reject if p̂ ≤ 0.85
                  ▼
            ┌───────────┐
            │  SENTINEL │  (risk)
            └─────┬─────┘
                  ▼
              [GATE 3: RISK]   ── reject if inventory/drawdown breach
                  ▼
            ┌───────────┐
            │ EXECUTOR  │  (paper trade)
            └───────────┘
```

Each gate is independent. A trade fires only if all three approve.

---

## 8. Backtest design

### Split

| Phase | Window | Use |
|---|---|---|
| Train | T − 21 d → T − 7 d (14 d) | Model fitting |
| Validation | T − 7 d → T − 3 d (4 d) | Threshold + hyperparameter selection |
| Holdout | T − 3 d → T (3 d) | Reported metrics, locked at end of May 14 |

Walk-forward only — no shuffling. We retrain weekly in the simulated production loop.

### Fill model

- **Aggressive (taker) fills** against displayed L2 depth at `t + 50 ms` (realistic order placement delay).
- **Fee schedule:** live taker rate from each venue, refreshed hourly.
- **Slippage:** 1-tick conservative pad on top of depth-walked fill price.
- **Partial fills:** if depth insufficient at `t + 50 ms`, label as `failure_unwind` and trigger Sentinel logic.

### Reported metrics (in this order)

1. **Cumulative post-fee P&L** (chart)
2. **Sharpe ratio** (annualized, post-fee)
3. **Hit rate** (fraction of fired trades with post-fee P&L > 0)
4. **Precision-at-threshold** of the Guardian
5. **Reliability diagram** (calibration plot)
6. **Failure-unwind frequency** (Sentinel events per 1000 candidate cycles)
7. **Latency p50 / p95** end-to-end

---

## 9. Third generic criterion: PostgreSQL

### Why SQL not dashboard, not VPS

- **Dashboard:** Streamlit/Dash adds frontend code that takes a week we don't have, and doesn't help model quality.
- **VPS deployment:** Infrastructure-only; doesn't differentiate the strategy. Andrea may add this, but it can't be the *third criterion* because the rubric wants substantive code.
- **SQL DB:** Genuinely needed (we have to store ticks, cycles, features, model versions), graders see it as substantive engineering, and it directly improves backtest reproducibility.

### Schema (PostgreSQL 15+)

```sql
CREATE TABLE book_snapshots (
  id            BIGSERIAL PRIMARY KEY,
  venue         TEXT NOT NULL,
  symbol        TEXT NOT NULL,
  ts            TIMESTAMPTZ NOT NULL,
  bid_px        NUMERIC(20,10), bid_sz NUMERIC(20,10),
  ask_px        NUMERIC(20,10), ask_sz NUMERIC(20,10),
  depth5_bids   JSONB, depth5_asks JSONB
);
CREATE INDEX ON book_snapshots (venue, symbol, ts DESC);

CREATE TABLE cycles_detected (
  id              BIGSERIAL PRIMARY KEY,
  ts              TIMESTAMPTZ NOT NULL,
  venue           TEXT NOT NULL,
  legs            JSONB NOT NULL,           -- [{from,to,rate}, ...]
  raw_log_return  NUMERIC(20,10) NOT NULL,
  expected_return NUMERIC(20,10) NOT NULL,  -- after fees
  passed_profit   BOOLEAN NOT NULL,
  features        JSONB                     -- denormalized ML features
);

CREATE TABLE trades_simulated (
  id              BIGSERIAL PRIMARY KEY,
  cycle_id        BIGINT REFERENCES cycles_detected(id),
  ts_signal       TIMESTAMPTZ NOT NULL,
  ts_filled       TIMESTAMPTZ,
  p_hat           NUMERIC(6,4) NOT NULL,    -- calibrated Guardian score
  passed_confidence BOOLEAN NOT NULL,
  passed_risk     BOOLEAN NOT NULL,
  realized_return NUMERIC(20,10),           -- NULL if not fired
  failure_unwind  BOOLEAN DEFAULT false,
  model_version   TEXT NOT NULL
);

CREATE TABLE model_versions (
  version         TEXT PRIMARY KEY,
  trained_at      TIMESTAMPTZ NOT NULL,
  algo            TEXT NOT NULL,            -- 'lightgbm' | 'random_forest'
  feature_set     JSONB NOT NULL,
  hyperparams     JSONB NOT NULL,
  val_auc         NUMERIC(6,4),
  val_precision_at_threshold NUMERIC(6,4),
  artifact_path   TEXT NOT NULL             -- S3 or local
);
```

### What this enables

- Walk-forward backtests are SQL-driven, not pickle-driven.
- Model lineage is auditable for the rubric ("traceability").
- Every result in the report is reproducible from the DB + a model version string.

---

## 10. Repository layout (proposal)

```
CRYPTO-ABRITRAGE-TRADING-BOT/
├── README.md
├── AGENTS.md                  ← see separate file
├── TECHNICAL_PLAN.md          ← this document
├── docs/
│   ├── diary.md               ← project diary, one paragraph per session
│   ├── architecture.md        ← Triple-Gate architecture deep-dive
│   ├── backtest_results.md    ← updated each model-train run
│   └── lessons_learned.md     ← market-efficiency reflections
├── report/
│   ├── main.tex               ← 5–8 page LaTeX report
│   └── figures/
├── src/
│   ├── scout/                 ← CCXT Pro WebSocket clients (Andrea)
│   ├── brain/                 ← graph + Bellman-Ford + Profit Gate (Giacomo)
│   ├── guardian/              ← features + LightGBM + RF (Edoardo)
│   ├── sentinel/              ← inventory + drawdown (shared)
│   ├── executor/              ← paper-trade simulator
│   └── db/                    ← schema + migrations + repositories
├── tests/                     ← pytest, target ≥70% coverage
├── ci/                        ← GitHub Actions workflows
├── notebooks/                 ← exploratory only, not production
└── pyproject.toml
```

---

## 11. Roadmap (locked)

| Date | Milestone | Owner anchors |
|---|---|---|
| **Apr 30** | Repo init, AGENTS.md, TECHNICAL_PLAN.md, Profit Gate spec | Edoardo |
| **May 7** | Scout streaming live, Brain + Profit Gate, DB schema | Andrea, Giacomo |
| **May 14** | Guardian trained, calibrated, walk-forward backtest harness | Edoardo |
| **May 22** | Sentinel integrated, repo freeze, LaTeX report submitted | All |

---

## 12. Risks we are accepting (state them honestly)

1. **Holdout may show negative post-fee P&L.** This is acceptable if the academic framing holds: a falsified hypothesis is still a result. We will report it honestly with attribution.
2. **CCXT Pro is rate-limited.** We mitigate by sampling at 100 ms cadence rather than tick-by-tick. The trade-off is documented in `lessons_learned.md`.
3. **Model drift over the 3-day holdout.** With 3 days of data and ~3 retrain cycles, drift detection is impossible. We document this as a methodological caveat.
4. **No real venue execution.** All P&L is paper. We claim *no* statement about live profitability — only about the gating subset's behaviour on replayed historical books.

---

*Document version 1.0 — May 6, 2026. Update via PR; tag `[AI-AGENT-CONTRIBUTION]` if the change comes from an AI agent.*
