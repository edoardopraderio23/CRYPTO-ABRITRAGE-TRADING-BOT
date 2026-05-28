# User guide — Project Omni-Arb

This guide walks through running the system end-to-end, from a fresh clone of
the repository to inspecting backtest results.

---

## 1. Prerequisites

- macOS, Linux, or Windows (WSL2)
- Python 3.11 or higher
- PostgreSQL 15+ running locally (we use [Postgres.app](https://postgresapp.com/) on Mac)
- ~500 MB of free disk for the trained model and accumulated order-book data
- Network access to the four exchanges (Binance, Bybit, Coinbase, Kraken)

## 2. One-time setup

```bash
git clone https://github.com/edoardopraderio23/CRYPTO-ARBITRAGE-TRADING-BOT.git
cd CRYPTO-ARBITRAGE-TRADING-BOT
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
createdb omniarb
psql omniarb -f src/db/schema.sql
cp .env.example .env
# edit .env, set DATABASE_URL=postgresql://localhost:5432/omniarb
```

## 3. Daily workflow

### Step 1 — Start the data pipeline

```bash
./scripts/start_pipeline.sh
```

This script does five things:
1. Activates the virtual environment.
2. Sets `DATABASE_URL` to your local Postgres.
3. Kills any lingering Scout or emitter processes from a previous run.
4. Launches the Scout streamer (writes order books to `book_snapshots`).
5. Launches the cycle emitter (writes triangular cycles to `cycles_detected`).

It prints the PIDs of both processes, the current per-venue row counts, and
instructions for tailing the logs.

### Step 2 — Prevent your Mac from sleeping

In a separate Terminal tab:

```bash
caffeinate -i
```

Leave the tab open. The Mac stays awake as long as this command runs.

### Step 3 — Monitor progress

After at least 1 hour (recommended: 24 hours):

```bash
python scripts/check_data.py
```

This prints per-venue row counts in `book_snapshots` and total counts in
`cycles_detected`. Target: 200,000+ snapshots per venue before training.

### Step 4 — Stop the pipeline when you have enough data

```bash
./scripts/stop_pipeline.sh
```

## 4. Training the Guardian ML model

```bash
python scripts/train_guardian.py
```

Outputs:
- `models/guardian_v1_<timestamp>.joblib` — trained model bundle
- `reports/guardian_metrics.json` — AUC, precision, recall
- `reports/guardian_pr_curve.png` — precision-recall plot

The script uses a chronological 70/15/15 train/validation/test split, fits
LightGBM, calibrates probabilities via isotonic regression, picks the F1-optimal
threshold, and reports out-of-sample metrics on the test set.

## 5. Running the backtest

```bash
python scripts/run_backtest.py
```

Outputs:
- `reports/backtest_metrics.json` — per-scenario, per-strategy metrics
- `reports/equity_curves.png` — cumulative P&L plot (frictionless scenario)
- `reports/strategy_comparison.png` — bar chart across all three scenarios

The backtest evaluates three strategies (Random, Pre-fee Oracle, Guardian)
under three fee scenarios (realistic taker, maker rebate, frictionless).

## 6. Compiling the report

### Option A — Overleaf (recommended)

1. Create a free account at https://overleaf.com
2. Create a new project, upload `report/main.tex` and the three PNG files
   from `reports/`
3. In `main.tex`, change `\includegraphics{../reports/...}` to use just the
   filename (since plots and main.tex are now in the same Overleaf folder)
4. Click **Recompile** → PDF appears

### Option B — Local MacTeX

```bash
brew install --cask mactex
cd report
pdflatex main.tex
open main.pdf
```

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pkill` says "no process found" | Process already stopped | Safe to ignore |
| `psql: connection refused` | Postgres.app not running | Open Postgres.app from Applications, click Start |
| `ModuleNotFoundError: structlog` | venv not activated | `source .venv/bin/activate` |
| Scout writes 0 rows for one venue | Venue-specific depth rejected | Check `src/scout/streamer.py` `DEPTH_LIMIT_BY_VENUE` |
| Emitter writes 0 cycles | Repo/schema mismatch | Check `\d cycles_detected` matches `CycleRepo.insert()` |
| Mac goes to sleep overnight | `caffeinate -i` died | Restart in a new terminal tab; also set System Settings → Battery → Options → Prevent automatic sleeping ON |

## 8. Reproducing the v0.2.0 release

```bash
git checkout v0.2.0
pip install -r requirements.txt
psql omniarb -f src/db/schema.sql
# data must be regenerated since we don't commit book_snapshots
./scripts/start_pipeline.sh
# wait at least 12 hours for cycles to accumulate
python scripts/train_guardian.py
python scripts/run_backtest.py
```
