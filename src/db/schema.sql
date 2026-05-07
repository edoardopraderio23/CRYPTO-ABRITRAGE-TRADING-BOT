-- =============================================================
-- Project Omni-Arb · PostgreSQL schema (v0.1.0)
--
-- Four core tables capturing the full audit trail from raw
-- order-book event to simulated paper trade.
--
-- Aligned with TECHNICAL_PLAN.md §9.
-- Target: PostgreSQL 15+
-- =============================================================

-- -----------------------------------------------------------------
-- 1. book_snapshots
-- Raw L2 order-book observations from the Scout.
-- Indexed by (venue, symbol, ts) for fast walk-forward replay.
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS book_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    venue         TEXT        NOT NULL,
    symbol        TEXT        NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,
    bid_px        NUMERIC(20, 10),
    bid_sz        NUMERIC(20, 10),
    ask_px        NUMERIC(20, 10),
    ask_sz        NUMERIC(20, 10),
    depth5_bids   JSONB,
    depth5_asks   JSONB,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_book_snapshots_venue_symbol_ts
    ON book_snapshots (venue, symbol, ts DESC);

-- -----------------------------------------------------------------
-- 2. cycles_detected
-- Every triangular cycle the Brain emits, whether or not it passed
-- the Profit Gate. Denormalised features for downstream ML.
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cycles_detected (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL,
    venue           TEXT        NOT NULL,
    legs            JSONB       NOT NULL,            -- [{from, to, rate}, ...]
    raw_log_return  NUMERIC(20, 10) NOT NULL,
    expected_return NUMERIC(20, 10) NOT NULL,        -- after fees
    passed_profit   BOOLEAN     NOT NULL,
    rejection_reason TEXT,                           -- nullable; null iff passed_profit=true
    features        JSONB,                           -- ML features at signal time
    inserted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cycles_detected_ts
    ON cycles_detected (ts DESC);
CREATE INDEX IF NOT EXISTS ix_cycles_detected_passed
    ON cycles_detected (passed_profit, ts DESC);

-- -----------------------------------------------------------------
-- 3. trades_simulated
-- Outcome of a candidate cycle once the Confidence and Risk gates
-- have run. realized_return is NULL if the trade was not fired.
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trades_simulated (
    id                BIGSERIAL PRIMARY KEY,
    cycle_id          BIGINT      NOT NULL REFERENCES cycles_detected(id),
    ts_signal         TIMESTAMPTZ NOT NULL,
    ts_filled         TIMESTAMPTZ,
    p_hat             NUMERIC(6, 4) NOT NULL,        -- calibrated Guardian score
    passed_confidence BOOLEAN     NOT NULL,
    passed_risk       BOOLEAN     NOT NULL,
    fired             BOOLEAN     GENERATED ALWAYS AS
                                  (passed_confidence AND passed_risk) STORED,
    expected_return   NUMERIC(20, 10) NOT NULL,
    realized_return   NUMERIC(20, 10),
    failure_unwind    BOOLEAN     NOT NULL DEFAULT false,
    model_version     TEXT        NOT NULL REFERENCES model_versions(version),
    inserted_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_trades_simulated_ts
    ON trades_simulated (ts_signal DESC);
CREATE INDEX IF NOT EXISTS ix_trades_simulated_model_version
    ON trades_simulated (model_version, ts_signal DESC);
CREATE INDEX IF NOT EXISTS ix_trades_simulated_fired
    ON trades_simulated (fired, ts_signal DESC);

-- -----------------------------------------------------------------
-- 4. model_versions
-- Lineage for every trained Guardian model. Every row in
-- trades_simulated must reference a model_versions row, so we can
-- always reproduce a backtest by version string.
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_versions (
    version                       TEXT        PRIMARY KEY,    -- semver, e.g. "v0.1.0"
    trained_at                    TIMESTAMPTZ NOT NULL,
    algo                          TEXT        NOT NULL,       -- 'lightgbm' | 'random_forest'
    feature_set                   JSONB       NOT NULL,
    hyperparams                   JSONB       NOT NULL,
    train_window_start            TIMESTAMPTZ NOT NULL,
    train_window_end              TIMESTAMPTZ NOT NULL,
    val_auc                       NUMERIC(6, 4),
    val_precision_at_threshold    NUMERIC(6, 4),
    decision_threshold            NUMERIC(6, 4) NOT NULL DEFAULT 0.85,
    artifact_path                 TEXT        NOT NULL,
    notes                         TEXT,
    inserted_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------
-- View: gated_trade_pnl
-- Convenience view: only the trades that fired, with realized P&L
-- net of fees. Used by the backtest reporter.
-- -----------------------------------------------------------------
CREATE OR REPLACE VIEW gated_trade_pnl AS
SELECT
    t.id,
    t.ts_signal,
    t.ts_filled,
    t.model_version,
    t.p_hat,
    t.expected_return,
    t.realized_return,
    t.failure_unwind,
    c.venue,
    c.legs
FROM trades_simulated t
JOIN cycles_detected   c ON c.id = t.cycle_id
WHERE t.fired = true;

-- =============================================================
-- End of schema.sql
-- =============================================================
