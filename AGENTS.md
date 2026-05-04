# AGENTS.md — Project Omni-Arb

This file governs how AI agents collaborate with the human team on Project Omni-Arb. It is required by the course rubric ("Provide as minimum an AGENTS.md file") and by our own audit-trail commitment.

**Read this before opening any PR. Agents that do not follow these rules will have their PRs rejected, regardless of code quality.**

---

## 1. The team

| Agent | Type | Owner | Scope |
|---|---|---|---|
| Andrea Cammarano | Human | Infrastructure | `src/scout/`, `src/db/`, `ci/`, deployment |
| Giacomo Lanni | Human | Quant | `src/brain/`, `src/executor/`, math in `report/` |
| Edoardo Praderio | Human | ML & workflow | `src/guardian/`, `src/sentinel/`, `AGENTS.md`, this file |
| GPT-4o ("Junior Quant") | AI | Code, tests, docs | Anywhere a human assigns it via issue |
| Claude / other LLMs | AI | Same as above | Same as above |

Agents are explicitly framed as **junior quantitative developers**. They write code, draft tests, refactor, and produce documentation — under human review. They do not own architectural decisions and do not merge their own PRs.

---

## 2. Mandatory PR conventions

### 2.1 Tagging
Every commit message and PR title authored (in whole or substantial part) by an AI agent **must** start with `[AI-AGENT-CONTRIBUTION]`.

Examples:
- `[AI-AGENT-CONTRIBUTION] feat(brain): add Bellman-Ford incremental update`
- `[AI-AGENT-CONTRIBUTION] test(guardian): add calibration plot regression test`
- `feat(brain): formalize edge-weight equation in math.tex` (human-only — no tag)

If a PR mixes human and agent commits, tag the PR title and tag only the agent commits within.

### 2.2 PR template
Every PR (human or agent) must answer, in the description:

```markdown
## What
<one-sentence summary>

## Why
<link to issue or rationale>

## How
<bulleted list of the actual changes>

## Agent disclosure
- [ ] No AI agent contribution
- [ ] AI agent drafted parts of this PR (which agent: ___, which sections: ___)
- [ ] AI agent fully drafted this PR (reviewer must verify all logic)

## Tests
<commands to reproduce; coverage delta if relevant>

## Risk
<what could break, what we measured, what we couldn't>
```

### 2.3 Mandatory rubric: at least one AI-agent PR before May 22
The rubric requires "at least one pull request made by an AI agent." We aim for ≥3, all merged before the May 14 milestone (so they don't get rushed).

---

## 3. Scope boundaries (what agents may and may not do)

### 3.1 Always allowed (no prior approval)
- Drafting unit tests against a written spec
- Refactoring within a single file with no behaviour change
- Writing or improving docstrings, README sections, or `docs/*.md`
- Running formatters (black, ruff) and proposing the diff
- Generating boilerplate (DB migrations from a schema, type stubs)

### 3.2 Allowed only with an open issue assigned to the agent
- Implementing a function whose signature and contract is in the issue
- Adding or removing dependencies (must be approved in the issue)
- Touching files under `src/brain/`, `src/guardian/`, `src/sentinel/`, `src/executor/`

### 3.3 Never (human only, no exceptions)
- **Defining or changing the labeling rule** for the Guardian (financial logic)
- **Choosing the decision threshold** (`p_hat > 0.85` is locked)
- **Modifying the fee schedule** or slippage buffer in production code
- **Force-pushing**, rewriting history, or merging their own PR
- **Disabling tests, CI checks, or pre-commit hooks**
- **Touching `secrets/`, `.env*`, or anything under `infra/credentials/`**
- **Opening a PR that mixes a feature change with a refactor in the same diff**

---

## 4. Human-in-the-loop review gates

Some changes require a human review even if the agent's PR is otherwise clean. These are the "financial logic" gates.

| Path or topic | Mandatory reviewer |
|---|---|
| `src/brain/` (cycle detection, edge weights, profit gate) | Giacomo |
| `src/guardian/` (features, model, calibration, threshold) | Edoardo |
| `src/sentinel/` (risk caps, drawdown halt, leg-failure unwinds) | Edoardo + one of {Andrea, Giacomo} |
| `src/db/` (schema migrations) | Andrea |
| `report/` (anything published) | All three humans |
| Anything tagged `safety` or `correctness` in CI | Two humans |

A human review here means: the human re-derives or re-justifies the math, runs the test suite locally, and writes "Approved — verified [X]" in the PR comment. A 👍 reaction is not enough.

---

## 5. Resumption from a drawdown halt

If the Sentinel triggers a drawdown halt (24-h paper P&L < μ − 2σ), the system writes a halt event and stops firing trades. To resume:

1. A human investigates: feature drift, regime change, code regression?
2. The human opens a PR titled `[HALT-ACK] resume after <date> <reason>`.
3. The PR must include a brief postmortem in `docs/halts.md`.
4. Two humans must approve.
5. Resumption is automatic on merge.

No agent may open a `[HALT-ACK]` PR.

---

## 6. Prompt provenance

When an agent produces non-trivial code, the prompt that produced it goes in the PR description under `## Prompt provenance` — verbatim if it fits in <100 lines, otherwise as a link to a markdown file in `docs/prompts/<date>_<slug>.md`. This protects the rubric's traceability requirement and helps us understand what the agent was actually asked.

---

## 7. CI rules that affect agents

The CI pipeline runs on every push:

| Check | Blocking? | Notes |
|---|---|---|
| `pytest` (unit + integration) | yes | ≥70% coverage on `src/` |
| `mypy --strict` on `src/guardian/`, `src/brain/` | yes | Loose on `src/scout/`, `notebooks/` |
| `ruff` lint | yes | Config in `pyproject.toml` |
| Latency-budget benchmark | yes | p95 regression >20% fails |
| Calibration regression on Guardian | yes | After May 14 |
| AI tag verification | yes | If commit message lacks `[AI-AGENT-CONTRIBUTION]` and PR is flagged AI-authored, CI fails |

CI fails close the PR. Agents must read the CI output and fix the issue, not bypass it.

---

## 8. What agents should produce well

### 8.1 Tests
- Use `pytest`, fixtures over setup, parametrize over duplication.
- Property-based tests via `hypothesis` are encouraged for the Brain (graph invariants) and the Profit Gate (monotonicity of fee filter).
- Replay-fixture data lives in `tests/fixtures/replays/` — never make tests depend on live exchange calls.

### 8.2 Documentation
- Docstrings: NumPy style. Include `Parameters`, `Returns`, `Raises`, `Examples`.
- Module-level docstrings explain the *what* and the *why* — not the *how* (the code is the how).
- `docs/diary.md` gets one paragraph per work session, ideally written by the human at session end. Agents may *propose* diary entries but humans must verify and commit them.

### 8.3 Refactors
- One concern per PR. Renames separate from logic changes. Test coverage must not drop.
- If the diff is over 400 lines, split it.

---

## 9. What a good agent PR looks like

Example title: `[AI-AGENT-CONTRIBUTION] test(brain): property-based test for negative-cycle detection invariants`

Example description:
```markdown
## What
Adds 12 property-based tests for the Bellman-Ford negative-cycle detector in `src/brain/cycles.py`.

## Why
Closes #42. Coverage on `src/brain/cycles.py` was 78% with no edge-case property tests.

## How
- New file `tests/brain/test_cycles_properties.py` using `hypothesis`.
- Tests cover: graph with no negative cycle, graph with single 3-cycle, graph with overlapping cycles, numerical stability under float noise.

## Agent disclosure
- [x] AI agent fully drafted this PR (reviewer must verify all logic)
  - Agent: Claude
  - Sections: all of `tests/brain/test_cycles_properties.py`

## Tests
`pytest tests/brain/test_cycles_properties.py -v` — 12 passed in 1.3s.
Coverage delta: 78% → 91%.

## Risk
The property-based tests rely on `hypothesis` strategies that I (the agent) defined. A human should verify the strategies actually exercise the failure modes we care about, not just the happy path.

## Prompt provenance
See `docs/prompts/2026-05-04_brain_cycles_properties.md`.
```

This PR is mergeable after one human review (Giacomo, since it touches `src/brain/`).

---

## 10. Versioning of this file

Changes to `AGENTS.md` itself require approval from all three humans. Agents may not modify this file except via a PR that one of the humans has explicitly requested.

*Last updated: May 6, 2026 — initial version.*
