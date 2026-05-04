# Project Omni-Arb

**Selection-driven triangular arbitrage with risk-aware ML filtering and post-fee profitability gating.**

Crypto markets in 2026 are dominated by HFT firms that own raw latency. After fees, the median triangular cycle on Binance, Kraken, or Coinbase is unprofitable. Our edge is not speed — it is *selection*: deciding which of the surviving cycles will actually execute as priced.

> *Knowing when not to trade is the alpha.*

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Status: Active Development](https://img.shields.io/badge/status-active%20development-orange.svg)]()
[![License: Academic](https://img.shields.io/badge/license-academic-lightgrey.svg)]()

This is the final-project repository for **USI · Master in Finance Y1 · Programming in Finance & Economics II (2026)**.

---

## Table of contents

- [Overview](#overview)
- [The Triple-Gate architecture](#the-triple-gate-architecture)
- [Quick start](#quick-start)
- [Project structure](#project-structure)
- [Running a paper-trade simulation](#running-a-paper-trade-simulation)
- [Configuration](#configuration)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [Team](#team)
- [Documentation](#documentation)
- [Disclaimer](#disclaimer)

---

## Overview

Project Omni-Arb scans for triangular arbitrage opportunities across three exchanges (Binance, Kraken, Coinbase) and decides whether to fire a simulated trade through three independent rejection filters:

1. **Profit Gate** — pure math: does expected return exceed fees plus a slippage buffer?
2. **Confidence Gate** — calibrated ML: will the cycle actually execute within 5 bps of the mid-price?
3. **Risk Gate** — inventory and drawdown controls: can we afford to lose this trade?

A cycle fires only if **all three gates approve**. The system runs in paper-trade mode only — no live execution.

### What this project is

- A research-grade testbed for studying crypto market efficiency at retail latency.
- A demonstrably correct walk-forward backtest with fee-aware fill simulation.
- An audit-trail-first agentic workflow (see [`AGENTS.md`](./AGENTS.md)).

### What this project is not

- A production trading bot. We make **no claim** about live profitability.
- A latency-optimised system. Realistic end-to-end latency is ~19 ms p50 / ~32 ms p95 in Python — far slower than HFT competitors.
- Financial advice.

---

## The Triple-Gate architecture

```
              ┌───────────┐
WebSocket ───▶│   SCOUT   │  CCXT Pro · L2 depth-5 · 100 ms cadence
              └─────┬─────┘
                    ▼
              ┌───────────┐
              │   BRAIN   │  Bellman-Ford negative-cycle detection
              └─────┬─────┘
                    ▼
                [GATE 1: PROFIT]   reject if ROI ≤ fees + 5 bps buffer
                    ▼
              ┌───────────┐
              │  GUARDIAN │  LightGBM (production) + Random Forest (baseline)
              └─────┬─────┘
                    ▼
                [GATE 2: CONFIDENCE]   reject if calibrated p̂ ≤ 0.85
                    ▼
              ┌───────────┐
              │  SENTINEL │  inventory cap · drawdown halt · leg-failure unwind
              └─────┬─────┘
                    ▼
                [GATE 3: RISK]   reject if inventory or drawdown breach
                    ▼
              ┌───────────┐
              │ EXECUTOR  │  paper-trade simulator
              └───────────┘
```

Full architectural rationale, including the labeling rule, latency budget, and backtest design, lives in [`TECHNICAL_PLAN.md`](./TECHNICAL_PLAN.md).

---

## Quick start

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 15+ running locally (or accessible via `DATABASE_URL`)
- A Binance / Kraken / Coinbase account (read-only API keys are sufficient — we do not place real orders)

### Install

```bash
# 1. Clone
git clone https://github.com/edoardopraderio23/CRYPTO-ARBITRAGE-TRADING-BOT.git
cd CRYPTO-ARBITRAGE-TRADING-BOT

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure (see Configuration below)
cp .env.example .env
# edit .env with your DB URL and exchange API keys

# 5. Initialise the database
python -m src.db.init
```

---

## Project structure

```
CRYPTO-ARBITRAGE-TRADING-BOT/
├── README.md                  # this file
├── AGENTS.md                  # AI-agent collaboration rules (mandatory)
├── TECHNICAL_PLAN.md          # engineering specification
├── requirements.txt           # Python dependencies
├── .env.example               # configuration template
│
├── docs/
│   ├── presentation/
│   │   ├── SPEECH_SCRIPT.md   # 6-minute presenter script
│   │   └── Slides.pdf         # 3-slide deck
│   ├── architecture.md        # Triple-Gate deep dive
│   ├── diary.md               # development diary (one entry per session)
│   └── lessons_learned.md     # market-efficiency reflections
│
├── report/
│   ├── main.tex               # 5–8 page LaTeX academic report
│   └── figures/
│
├── src/
│   ├── scout/                 # CCXT Pro WebSocket clients (Andrea)
│   ├── brain/                 # graph + Bellman-Ford + Profit Gate (Giacomo)
│   ├── guardian/              # features + LightGBM + RF (Edoardo)
│   ├── sentinel/              # inventory + drawdown (shared)
│   ├── executor/              # paper-trade simulator
│   └── db/                    # schema + migrations + repositories
│
├── tests/                     # pytest suite, target ≥70% coverage
├── ci/                        # GitHub Actions workflows
└── notebooks/                 # exploratory analysis only
```

---

## Running a paper-trade simulation

The simplest entry point streams live order books, runs all three gates, and writes simulated trades to PostgreSQL. **No real orders are placed.**

```bash
# Single-venue, single-pair paper run (Binance · BTC-ETH-USDT, 60-second window)
python -m src.executor.run_paper \
    --venue binance \
    --pairs BTC-ETH-USDT \
    --duration 60 \
    --model-version v0.1.0
```

Output is written to the `trades_simulated` table:

```sql
SELECT
    ts_signal,
    p_hat,
    passed_confidence,
    passed_risk,
    realized_return
FROM trades_simulated
WHERE model_version = 'v0.1.0'
ORDER BY ts_signal DESC
LIMIT 20;
```

### Replaying a historical window (for backtests)

```bash
# Walk-forward replay over a 14-day window
python -m src.executor.replay \
    --start 2026-04-01 \
    --end   2026-04-14 \
    --venue binance \
    --model-version v0.1.0
```

Reported metrics (post-fee Sharpe, hit rate, calibration curve, precision-at-threshold, failure-unwind frequency, latency p50/p95) are written to `docs/backtest_results.md`.

---

## Configuration

All configuration is via environment variables. See `.env.example` for the full list.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | — | `postgresql://user:pass@host:5432/omni_arb` |
| `BINANCE_API_KEY` | yes | — | Read-only key is sufficient |
| `BINANCE_API_SECRET` | yes | — | |
| `KRAKEN_API_KEY` | yes | — | |
| `KRAKEN_API_SECRET` | yes | — | |
| `COINBASE_API_KEY` | yes | — | |
| `COINBASE_API_SECRET` | yes | — | |
| `SLIPPAGE_BUFFER_BPS` | no | `5` | Profit Gate slippage tolerance |
| `CONFIDENCE_THRESHOLD` | no | `0.85` | Guardian decision rule (locked, do not change without review) |
| `INVENTORY_CAP_USD` | no | `1000` | Sentinel inventory cap per non-base currency |
| `DRAWDOWN_SIGMA` | no | `2.0` | Sentinel drawdown halt tripwire |
| `LOG_LEVEL` | no | `INFO` | Standard Python logging levels |

> ⚠️ **Never commit `.env`.** API secrets, even read-only, do not belong in version control. The repository's `.gitignore` excludes it.

---

## Testing

```bash
# Unit + integration tests
pytest

# With coverage report
pytest --cov=src --cov-report=term-missing

# Property-based tests (Brain, Profit Gate)
pytest tests/brain/ -v
```

CI (GitHub Actions) runs the full suite on every push, plus `ruff` lint, `mypy --strict` on `src/guardian/` and `src/brain/`, and a latency-budget benchmark. A p95 latency regression of more than 20% fails the build.

---

## Roadmap

| Date | Milestone |
|---|---|
| **Apr 30** ✅ | Repository initialisation, `AGENTS.md`, `TECHNICAL_PLAN.md`, Profit Gate spec |
| **May 7** | Scout streaming live · Brain + Profit Gate integrated · DB schema deployed |
| **May 14** | Guardian trained and calibrated · backtest harness locked |
| **May 22** | Sentinel integrated · repo frozen · LaTeX report submitted |

Open issues and the project board track sub-tasks: see [Issues](../../issues) and [Projects](../../projects).

---

## Team

| Member | Role | Scope |
|---|---|---|
| **Andrea Cammarano** | Infrastructure & cloud | `src/scout/`, `src/db/`, `ci/`, deployment |
| **Giacomo Lanni** | Quant strategy & graph modelling | `src/brain/`, `src/executor/`, math sections of `report/` |
| **Edoardo Praderio** | ML intelligence & agent workflow | `src/guardian/`, `src/sentinel/`, `AGENTS.md` |
| **AI Associate (GPT-4o, Claude, etc.)** | Junior quant developer | Anywhere a human assigns it via issue. PRs tagged `[AI-AGENT-CONTRIBUTION]`. |

Human-in-the-loop review is mandatory for all financial logic. See [`AGENTS.md`](./AGENTS.md) §4 for review gates.

---

## Documentation

| Document | Purpose |
|---|---|
| [`AGENTS.md`](./AGENTS.md) | AI-agent collaboration rules (rubric requirement) |
| [`TECHNICAL_PLAN.md`](./TECHNICAL_PLAN.md) | Full engineering specification: latency budget, ML labelling rule, backtest design, schema, risks |
| [`docs/architecture.md`](./docs/architecture.md) | Triple-Gate deep dive |
| [`docs/diary.md`](./docs/diary.md) | Development diary (one paragraph per session) |
| [`docs/lessons_learned.md`](./docs/lessons_learned.md) | Market-efficiency reflections |
| [`docs/presentation/SPEECH_SCRIPT.md`](./docs/presentation/SPEECH_SCRIPT.md) | 6-minute presenter script |
| [`report/main.tex`](./report/main.tex) | Academic report (5–8 pages) |

---

## Disclaimer

This project is an **academic exercise**. It runs in paper-trade mode only and makes no claim about live profitability. Triangular arbitrage at retail latency in 2026 is dominated by HFT firms — our explicit hypothesis is that the residual edge for a Python-based selection strategy is small or negative, and a falsified hypothesis is itself a valid academic result. Do not deploy this code with live capital.

---

*Last updated: May 4, 2026  ·  Project Omni-Arb v2.0*
