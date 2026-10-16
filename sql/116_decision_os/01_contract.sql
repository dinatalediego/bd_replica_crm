BEGIN;

CREATE SCHEMA IF NOT EXISTS decision_intelligence;

-- ---------------------------------------------------------------------------
-- Medallio Decision OS v1
-- Canonical additive layer over the existing decision/action/outcome ledgers.
-- Economic Value becomes a first-class, versioned and auditable object.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS decision_intelligence.economic_value_ledger (
    economic_value_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id text NOT NULL
        REFERENCES decision_intelligence.decision_ledger(decision_id)
        ON DELETE CASCADE,
    action_id text
        REFERENCES decision_intelligence.action_log(action_id)
        ON DELETE SET NULL,
    outcome_id text
        REFERENCES decision_intelligence.outcome_ledger(outcome_id)
        ON DELETE SET NULL,
    value_stage text NOT NULL
        CHECK (value_stage IN ('EXPECTED', 'APPROVED', 'REALIZED', 'COUNTERFACTUAL')),
    value_type text NOT NULL
        CHECK (value_type IN ('REVENUE', 'MARGIN', 'COST_SAVING', 'RISK_AVOIDED', 'OPPORTUNITY', 'OTHER')),
    value_name text NOT NULL,
    currency text NOT NULL DEFAULT 'PEN'
        CHECK (currency ~ '^[A-Z]{3}$'),
    baseline_value numeric,
    comparison_value numeric,
    direct_cost numeric NOT NULL DEFAULT 0,
    opportunity_cost numeric NOT NULL DEFAULT 0,
    net_incremental_value numeric NOT NULL,
    probability numeric
        CHECK (probability IS NULL OR (probability >= 0 AND probability <= 1)),
    confidence_pct numeric
        CHECK (confidence_pct IS NULL OR (confidence_pct >= 0 AND confidence_pct <= 100)),
    confidence_adjusted_value numeric GENERATED ALWAYS AS (
        net_incremental_value * COALESCE(confidence_pct, 100) / 100.0
    ) STORED,
    horizon_days integer
        CHECK (horizon_days IS NULL OR horizon_days >= 0),
    valuation_basis text NOT NULL DEFAULT 'NET_AFTER_COSTS',
    calculation_method text NOT NULL DEFAULT 'EXPECTED_VALUE',
    formula_version text NOT NULL DEFAULT 'v1',
    valuation_at timestamptz NOT NULL DEFAULT now(),
    source_artifact text,
    assumptions jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (action_id IS NULL OR decision_id IS NOT NULL),
    CHECK (outcome_id IS NULL OR decision_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_economic_value_decision_stage
    ON decision_intelligence.economic_value_ledger(decision_id, value_stage, valuation_at DESC);
CREATE INDEX IF NOT EXISTS ix_economic_value_action
    ON decision_intelligence.economic_value_ledger(action_id)
    WHERE action_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_economic_value_outcome
    ON decision_intelligence.economic_value_ledger(outcome_id)
    WHERE outcome_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS decision_intelligence.decision_reviews (
    review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id text NOT NULL
        REFERENCES decision_intelligence.decision_ledger(decision_id)
        ON DELETE CASCADE,
    review_type text NOT NULL
        CHECK (review_type IN ('DATA_SCIENCE', 'BUSINESS', 'FINANCE', 'RISK')),
    review_status text NOT NULL DEFAULT 'PENDING'
        CHECK (review_status IN ('PENDING', 'APPROVED', 'OBSERVED', 'REJECTED')),
    reviewer text,
    score_pct numeric
        CHECK (score_pct IS NULL OR (score_pct >= 0 AND score_pct <= 100)),
    comment text,
    review_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_decision_reviews_decision_type
    ON decision_intelligence.decision_reviews(decision_id, review_type, reviewed_at DESC);

-- Weakly-coupled bridge from ML/recommendation systems to a governed decision.
-- Text references are intentional: existing Medallio modules use several ID types.
CREATE TABLE IF NOT EXISTS decision_intelligence.decision_model_links (
    link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id text NOT NULL
        REFERENCES decision_intelligence.decision_ledger(decision_id)
        ON DELETE CASCADE,
    source_system text NOT NULL,
    model_name text,
    model_version text,
    prediction_reference text,
    recommendation_reference text,
    predicted_probability numeric
        CHECK (predicted_probability IS NULL OR (predicted_probability >= 0 AND predicted_probability <= 1)),
    treatment_effect numeric
        CHECK (treatment_effect IS NULL OR (treatment_effect >= -1 AND treatment_effect <= 1)),
    linked_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_decision_model_links_decision
    ON decision_intelligence.decision_model_links(decision_id, linked_at DESC);

CREATE OR REPLACE VIEW decision_intelligence.v_economic_value_reconciliation AS
WITH agg AS (
    SELECT
        decision_id,
        SUM(net_incremental_value) FILTER (WHERE value_stage IN ('EXPECTED', 'APPROVED')) AS expected_value,
        SUM(confidence_adjusted_value) FILTER (WHERE value_stage IN ('EXPECTED', 'APPROVED')) AS expected_confidence_adjusted_value,
        SUM(net_incremental_value) FILTER (WHERE value_stage = 'REALIZED') AS realized_value,
        MAX(valuation_at) AS latest_valuation_at
    FROM decision_intelligence.economic_value_ledger
    GROUP BY decision_id
)
SELECT
    d.decision_id,
    d.project_key,
    d.decision_title,
    d.decision_status,
    a.expected_value,
    a.expected_confidence_adjusted_value,
    a.realized_value,
    CASE
        WHEN a.expected_value IS NULL OR a.realized_value IS NULL THEN NULL
        ELSE a.realized_value - a.expected_value
    END AS value_gap,
    CASE
        WHEN NULLIF(a.expected_value, 0) IS NULL OR a.realized_value IS NULL THEN NULL
        ELSE a.realized_value / NULLIF(a.expected_value, 0)
    END AS realization_ratio,
    a.latest_valuation_at
FROM decision_intelligence.decision_ledger d
LEFT JOIN agg a ON a.decision_id = d.decision_id;

CREATE OR REPLACE VIEW decision_intelligence.v_decision_operating_system AS
WITH action_agg AS (
    SELECT
        decision_id,
        COUNT(*) AS action_count,
        COUNT(*) FILTER (WHERE upper(action_status) IN ('DONE', 'COMPLETED', 'EXECUTED', 'CLOSED')) AS completed_action_count,
        MAX(action_ts) AS latest_action_ts,
        SUM(COALESCE(action_cost_realized, 0)) AS action_cost_realized
    FROM decision_intelligence.action_log
    GROUP BY decision_id
),
outcome_agg AS (
    SELECT
        decision_id,
        COUNT(*) AS outcome_count,
        MAX(outcome_ts) AS latest_outcome_ts,
        SUM(COALESCE(value_realized, 0)) AS outcome_value_realized
    FROM decision_intelligence.outcome_ledger
    GROUP BY decision_id
),
review_agg AS (
    SELECT
        decision_id,
        MAX(reviewed_at) FILTER (WHERE review_type = 'DATA_SCIENCE') AS data_science_reviewed_at,
        MAX(review_status) FILTER (WHERE review_type = 'DATA_SCIENCE') AS data_science_review_status,
        MAX(reviewed_at) FILTER (WHERE review_type = 'BUSINESS') AS business_reviewed_at,
        MAX(review_status) FILTER (WHERE review_type = 'BUSINESS') AS business_review_status,
        AVG(score_pct) AS avg_review_score_pct
    FROM decision_intelligence.decision_reviews
    GROUP BY decision_id
),
model_agg AS (
    SELECT
        decision_id,
        COUNT(*) AS model_link_count,
        MAX(linked_at) AS latest_model_link_at
    FROM decision_intelligence.decision_model_links
    GROUP BY decision_id
)
SELECT
    d.*,
    COALESCE(a.action_count, 0) AS action_count,
    COALESCE(a.completed_action_count, 0) AS completed_action_count,
    a.latest_action_ts,
    COALESCE(a.action_cost_realized, 0) AS action_cost_realized,
    COALESCE(o.outcome_count, 0) AS outcome_count,
    o.latest_outcome_ts,
    COALESCE(o.outcome_value_realized, 0) AS outcome_value_realized,
    ev.expected_value,
    ev.expected_confidence_adjusted_value,
    ev.realized_value AS economic_value_realized,
    ev.value_gap,
    ev.realization_ratio,
    r.data_science_review_status,
    r.data_science_reviewed_at,
    r.business_review_status,
    r.business_reviewed_at,
    r.avg_review_score_pct,
    COALESCE(m.model_link_count, 0) AS model_link_count,
    m.latest_model_link_at,
    CASE
        WHEN ev.expected_value IS NULL THEN 'ECONOMIC_VALUE_MISSING'
        WHEN r.data_science_review_status IS NULL THEN 'DATA_SCIENCE_REVIEW_MISSING'
        WHEN r.business_review_status IS NULL THEN 'BUSINESS_REVIEW_MISSING'
        WHEN r.data_science_review_status = 'REJECTED' OR r.business_review_status = 'REJECTED' THEN 'BLOCKED'
        WHEN r.data_science_review_status IN ('APPROVED', 'OBSERVED')
         AND r.business_review_status IN ('APPROVED', 'OBSERVED') THEN 'READY_FOR_DECISION'
        ELSE 'REVIEW_PENDING'
    END AS readiness_status
FROM decision_intelligence.decision_ledger d
LEFT JOIN action_agg a ON a.decision_id = d.decision_id
LEFT JOIN outcome_agg o ON o.decision_id = d.decision_id
LEFT JOIN decision_intelligence.v_economic_value_reconciliation ev ON ev.decision_id = d.decision_id
LEFT JOIN review_agg r ON r.decision_id = d.decision_id
LEFT JOIN model_agg m ON m.decision_id = d.decision_id;

CREATE OR REPLACE VIEW decision_intelligence.v_decision_queue AS
SELECT
    decision_id,
    decision_ts,
    project_key,
    challenge,
    decision_title,
    owner,
    deadline,
    decision_status,
    decision_level,
    evidence_grade,
    gate_status,
    confidence,
    expected_roi,
    expected_value,
    expected_confidence_adjusted_value,
    economic_value_realized,
    value_gap,
    readiness_status,
    model_link_count,
    action_count,
    outcome_count,
    COALESCE(expected_confidence_adjusted_value, confidence_adjusted_value, value_to_capture, 0) AS priority_economic_value
FROM decision_intelligence.v_decision_operating_system
WHERE upper(COALESCE(decision_status, 'PROPOSED')) NOT IN ('DONE', 'CLOSED', 'REJECTED', 'CANCELLED', 'ARCHIVED')
ORDER BY
    CASE readiness_status
        WHEN 'READY_FOR_DECISION' THEN 1
        WHEN 'BUSINESS_REVIEW_MISSING' THEN 2
        WHEN 'DATA_SCIENCE_REVIEW_MISSING' THEN 3
        WHEN 'ECONOMIC_VALUE_MISSING' THEN 4
        WHEN 'REVIEW_PENDING' THEN 5
        ELSE 6
    END,
    COALESCE(expected_confidence_adjusted_value, confidence_adjusted_value, value_to_capture, 0) DESC,
    deadline NULLS LAST,
    decision_ts DESC;

COMMIT;
