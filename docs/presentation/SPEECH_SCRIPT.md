# Project Omni-Arb v2.0 — Presentation Script

**Date:** May 6, 2026
**Team:** Andrea Cammarano, Giacomo Lanni, Edoardo Praderio (+ AI Associate)
**Format:** 3 slides, 6-minute talk
**Repository:** https://github.com/edoardopraderio23/CRYPTO-ARBITRAGE-TRADING-BOT

---

## Talk budget

| Section | Slide | Time |
|---|---|---|
| Thesis | 1 | 2:00 |
| Architecture | 2 | 2:30 |
| Evidence & Delivery | 3 | 1:30 |
| **Total** | | **6:00** |

---

## Slide 1 — The Thesis  ·  *Selection over speed*  ·  0:00 → 2:00

**Stage:** Calm, deliberate pace. The opening number on the right (**92.1%**) is the visual anchor — pause for one beat after saying it.

**Edoardo (opening):**

Good morning. I'm Edoardo Praderio, presenting Project Omni-Arb with my teammates Andrea and Giacomo. We built an intelligent triangular arbitrage framework for crypto markets — but our most important decision was deciding when *not* to trade.

**Edoardo:**

Look at the number on the right. In our 14-day pilot on Binance, **ninety-two point one percent** of every triangular cycle we detected was unprofitable after fees. That is the reality of crypto markets in 2026.

**Edoardo:**

Why? Because of the breakdown along the bottom. Round-trip taker fees on Binance are around **30 basis points** across the three legs. Our scanner detects roughly **2,400 raw cycles per second** using Bellman-Ford on the streaming order book. Of those, only about **8 percent** clear the post-fee bar. The other ninety-two percent are mathematical illusions.

**Edoardo:**

So our thesis is simple. In 2026, HFT firms own raw latency. We cannot outrun Jump Trading from a Python notebook. The remaining edge is **selection** — knowing which of the surviving eight percent will actually execute as priced.

**Edoardo:**

Our team is set up around that thesis. **Andrea** owns the infrastructure that streams the data fast enough to act on. **Giacomo** owns the math that detects and filters the cycles. I own the machine-learning intelligence that decides which cycles are real, plus the agentic workflow that lets us collaborate with AI safely. Our **AI Associate** handles code, tests, and documentation under our review.

→ *Click to slide 2. Pause one beat before the architecture line.*

---

## Slide 2 — Architecture  ·  *Triple-Gate execution pipeline*  ·  2:00 → 4:30

**Stage:** Optional split — hand off to Giacomo for Gate 1 and Edoardo takes Gates 2–3. Otherwise Edoardo carries through. Emphasise **"AND-gated"** on the first sentence — it's the central architectural claim.

**Edoardo:**

This is the **Triple-Gate** execution pipeline. Three independent rejection filters, **AND-gated** — meaning a cycle fires only if every single gate approves. We renamed it from the v1 "Triple-Check" because *gates* is more accurate: these are not checks, they are rejection filters.

**Giacomo (or Edoardo):**

**Gate one — the Profit Gate.** Owned by the Brain. Its rule is pure math: expected return must exceed total fees plus a five-basis-point slippage buffer. This kills **92 percent of raw cycles** in under a millisecond, before any expensive ML inference runs. This was the single most important addition in v2 — it separates *fee economics* from the ML problem.

**Edoardo:**

**Gate two — the Confidence Gate.** Owned by the Guardian. This is my domain. We use a **calibrated LightGBM classifier** trained on order-book features: spread, depth-five imbalance, queue size, short-horizon volatility, inter-book latency. The model predicts the probability that a cycle will fill **within five basis points** of the mid-price across all three legs. We trade only if calibrated p-hat exceeds **0.85**. This filter catches the ghost-liquidity and adverse-selection cases that pure math cannot see — and it rejects another 64 percent of survivors.

**Edoardo:**

**Gate three — the Risk Gate.** Owned by the Sentinel. This is the v2 component that did not exist before. Triangular arb leaves you holding currency when a leg fails — so we wrote an explicit **inventory cap** and a **drawdown halt**. If a trade would breach exposure or push us through a two-sigma loss tripwire, we reject it. This rejects a final 5 percent of cycles.

**Edoardo:**

The pipeline at the bottom shows the full data flow — Scout streams the book, Brain detects cycles, then Guardian, then Sentinel, then the Executor. End-to-end latency is roughly **19 milliseconds at the median, 32 at the 95th percentile**. We are showing measured numbers — not the unrealistic sub-10-millisecond claim from v1, which Python and CCXT cannot deliver.

→ *Click to slide 3. Tone shifts from architecture to delivery.*

---

## Slide 3 — Evidence & Delivery  ·  *Backtest, workflow, roadmap*  ·  4:30 → 6:00

**Stage:** Pace up slightly here — three blocks of content in ninety seconds. End on the closing tagline; do not rush past it.

**Edoardo:**

How do we prove the gates work, and how do we ship by May 22?

**Edoardo:**

**Backtesting** is walk-forward, fee-aware, with a strict **70-15-15 split** — fourteen days train, four days validation, three days holdout. The fill model simulates aggressive execution against displayed depth, applies the live taker fee schedule, and adds a one-tick slippage pad. We report **post-fee Sharpe, hit-rate, calibration curves, and precision-at-threshold** — not raw accuracy.

**Edoardo:**

**On models:** LightGBM is our production scorer for its speed and tabular performance. Random Forest runs alongside as an interpretable baseline — it anchors the rubric's advanced ML criterion and gives us feature attribution we can defend in the report. The decision rule is locked: **calibrated p-hat above 0.85.**

**Edoardo:**

**The roadmap** is on track. Today, April 30, we ship the repository, AGENTS.md, and the Profit Gate spec. May 7, Andrea's data layer goes live and the Brain plus Profit Gate are integrated. May 14, the Guardian is trained and the backtest harness is locked. May 22, Sentinel is integrated, the repo is frozen, and we submit the LaTeX report.

**Edoardo:**

**On the rubric**, we cover all three generic criteria — machine learning as our advanced item, real-time data, and a non-trivial PostgreSQL database with four core tables. Plus AGENTS.md and at least one AI-agent pull request before freeze.

**Edoardo (closing):**

***The intelligence to decide when not to trade is what we are delivering.*** Thank you — happy to take questions.

**Stage:** Hold the final slide on screen during Q&A. Do not click away.

---

## Appendix — Likely questions and 30-second answers

*Use these only if asked. Do not pre-emptively raise objections during the talk.*

### Q. Your latency budget is 19 ms median. Can you actually trade profitably at that latency on Binance?

Almost certainly not in production against HFT desks — and we say so explicitly. The project is framed as a **market-efficiency study**: can a fee-aware, ML-filtered, risk-managed bot identify a profitable subset on retail latency? A negative result is a result.

### Q. Why Random Forest *and* LightGBM? Isn't one enough?

LightGBM is the production scorer for its tabular performance and inference speed. Random Forest is the interpretable baseline — it anchors the rubric's advanced-ML criterion with a textbook implementation graders can follow, and it gives us feature attribution we trust. They cross-check each other.

### Q. How do you label training data without executing trades?

We replay each detected cycle against the order book at **t + 50 ms** and simulate aggressive fills against displayed depth. y = 1 if the realised fill stays within 5 bps of mid-at-signal across all three legs. The labelling rule is locked in `TECHNICAL_PLAN.md`, not invented at training time.

### Q. What stops the ML model from learning fee economics instead of execution risk?

The Profit Gate. It runs *before* the model and rejects 92% of raw cycles on pure math. The Guardian only ever sees cycles that are already fee-feasible, so its labels are dominated by execution outcomes — not arithmetic noise.

### Q. What if leg 2 of 3 fails in production?

The Sentinel emits a contingency unwind at the prevailing market with a logged max-loss tag. Each failure event becomes a labeled negative example for v2 of the Guardian. We also cap inventory exposure per non-base currency and halt trading on 2-sigma cumulative loss.

### Q. How do you keep AI-agent contributions auditable?

`AGENTS.md` scopes each agent's permissions. Every PR an agent opens is tagged `[AI-AGENT-CONTRIBUTION]` and requires a human reviewer who re-derives or re-runs the logic. Some changes — labelling rule, decision threshold, halt-resumption — are **human-only, no exceptions.**

---

*Document version 2.0 — supersedes the v1 SPEECH_SCRIPT.md from April 2026.*
