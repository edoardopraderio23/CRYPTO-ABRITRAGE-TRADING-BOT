# Prompt provenance — `feat(sentinel): risk-adjusted capital allocator`

**Date:** 2026-05-07
**Agent:** Claude (Anthropic)
**Files produced:**
- `src/sentinel/allocator.py`
- `tests/sentinel/__init__.py` (empty package marker)
- `tests/sentinel/test_allocator.py`
- `conftest.py` (pytest path config — supporting infrastructure)

This file is committed per **AGENTS.md §6 (Prompt provenance)**.

---

## Human-supplied context

The agent was given:

1. **The architectural decision recorded in issue #1:** add Bybit as the
   fourth exchange, capital allocator should distribute paper-trade bankroll
   across the four venues using a Sharpe-like opportunity score.

2. **The exact scoring formula** (decided by the human team, not the agent):

   ```
   score_i = (freq_i × size_i × pass_rate_i) / sigma_i
   ```

3. **The exact allocation rule** (decided by the human team):

   ```
   floor_i  = max_trade_size_usd × LEGS_PER_CYCLE
   residual = bankroll_usd − N × floor_i
   w_i      = score_i / sum(score_j)
   cap_i    = floor_i + residual × w_i
   ```

4. **Constraints from AGENTS.md**:
   - The `src/sentinel/` package must satisfy `mypy --strict` (§7).
   - All financial-logic decisions remain with the human team (§3.3).
   - Tests must accompany the implementation (§8.1).

5. **Edge cases the human team flagged for explicit handling:**
   - All scores zero → equal-weight fallback (defensible: when data says
     nothing, treat venues symmetrically).
   - Bankroll too small to fund every floor → raise `ValueError` rather
     than silently shrink floors (this would change the meaning of the
     allocation in a way that should require human attention).
   - Negative or zero `sigma` → score = 0 (no historical data, can't
     size risk).

## What the agent decided autonomously

- The dataclass shapes (`VenueMetrics`, `AllocationResult`) and field names.
- Whether to expose the score function as public or private (made it
  private with a leading underscore — it's an implementation detail of
  the allocation rule).
- The structure and coverage of the test suite (13 tests across
  scoring, structural invariants, monotonicity, validation).
- The fallback behaviour when `total_score == 0` (equal weights, with
  rationale string explaining why).
- The use of `structlog.get_logger` for the audit trail entry (this
  matches the dependency already declared in `requirements.txt`).
- The `conftest.py` mechanism for making `src.*` importable from tests.

## What the agent did NOT decide

- The scoring formula itself (human-given, see #2 above).
- The threshold values (e.g. `LEGS_PER_CYCLE = 3` is from the Brain's
  graph model, not chosen by the agent).
- The `0.85` confidence threshold elsewhere in the system — this PR
  does not touch it.
- Whether the allocator should be triggered nightly or per-trade — this
  is an operational decision that lives outside this PR.

## Review checklist (for the human reviewer per AGENTS.md §4)

The reviewer (Edoardo + one of {Andrea, Giacomo}) should verify:

- [ ] The implemented formula matches the one in this provenance doc.
- [ ] The `floor_per_venue = max_trade_size × LEGS_PER_CYCLE` semantics
      are correct (one full triangular cycle's worth of capital).
- [ ] The fallback to equal weights when all scores are zero is the
      right behaviour, not an error.
- [ ] The test for `test_bankroll_too_small_for_floors_raises` reflects
      the intended semantics (raise rather than shrink floors silently).
- [ ] No financial constants are hard-coded that should live in `.env`.

If any of these fail review, request changes; the agent will revise.
