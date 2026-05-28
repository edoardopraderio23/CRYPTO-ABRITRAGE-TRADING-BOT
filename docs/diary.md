# Development diary — Project Omni-Arb

A chronological record of major working sessions, decisions taken, and tools
used. Per the course brief (PIF II 2026, §Academic documentation), this diary
documents process over product.

---

## Week 1 — April 21 → April 27: scoping and architecture

Decided on triangular arbitrage in crypto spot markets as the project topic
(criteria 2.3 in the brief). Drafted the Triple-Gate architecture
(Profit Gate, Confidence Gate, Risk Gate) and the AGENTS.md governance
document. Tools: Anthropic Claude for brainstorming the gate decomposition;
Google Docs for the initial project plan. Outcome: TECHNICAL_PLAN.md v1
checked into the repo on Apr 25.

## Week 2 — April 28 → May 4: data infrastructure

Andrea built the Scout streamer (CCXT Pro) and the PostgreSQL schema.
Giacomo started the Bellman--Ford negative-cycle detector in `src/brain/`.
First end-to-end smoke test on Binance only. Realised the original schema
had `cycles_detected` indexes defined before tables — fixed in PR #12.
Tools: VS Code, CCXT Pro docs, PostgreSQL 16.

## Week 3 — May 5 → May 11: Brain + Profit Gate

Giacomo finished cycles.py and profit_gate.py with property-based tests via
hypothesis. Edoardo started the Guardian feature engineering. Decision:
expand from 3 to 4 venues by adding Bybit (Issue #1 records the rationale —
better depth profile, complements Coinbase's slower liquidity).

## Week 4 — May 12 → May 18: ML training pipeline

Edoardo built `src/guardian/train.py` with LightGBM + Random Forest +
isotonic calibration. Hit a real obstacle: the labelling rule originally
required replaying each cycle against next-tick books, but the test window
had insufficient positives at retail fees, so we pivoted to using
`raw_log_return > 0` as a leak-free training label. Tools: Claude for
the labelling pivot discussion, scikit-learn, LightGBM 4.x.

## Week 5 — May 19 → May 27: backtest, report, polish

Wrote the cycle emitter to enumerate all triangles (not just profitable
ones, which was the original bug — produced zero training data in efficient
markets). Ran the three-scenario backtest (realistic / maker / frictionless)
and discovered the empirical efficient-markets finding (zero positive-EV
trades under retail fees). Drafted the LaTeX report, polished the README,
tagged v0.2.0 release.

---

## Key tools used throughout

- **Languages / runtime**: Python 3.13, PostgreSQL 16
- **Libraries**: CCXT Pro, psycopg2, LightGBM, scikit-learn, structlog, pytest, hypothesis
- **Infrastructure**: Postgres.app (Mac), GitHub Actions for CI
- **AI assistants**: Anthropic Claude, OpenAI ChatGPT (see Acknowledgements in `report/main.tex`)
- **Writing**: LaTeX (Overleaf or local MacTeX), Markdown
- **Project management**: GitHub Issues + Projects board
