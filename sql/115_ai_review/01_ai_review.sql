BEGIN;

CREATE SCHEMA IF NOT EXISTS decision_intelligence;

CREATE TABLE IF NOT EXISTS decision_intelligence.ai_review_run (
    run_id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    project_ref text NOT NULL,
    context_sha256 text NOT NULL,
    packet_sha256 text NOT NULL,
    response_id text,
    model text,
    usage_json jsonb,
    review_json jsonb NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT_REVIEW_REQUIRED'
        CHECK (status = 'DRAFT_REVIEW_REQUIRED')
);

CREATE TABLE IF NOT EXISTS decision_intelligence.ai_review_finding (
    run_id text NOT NULL REFERENCES decision_intelligence.ai_review_run(run_id),
    finding_index integer NOT NULL CHECK (finding_index BETWEEN 0 AND 2),
    category text NOT NULL,
    priority text NOT NULL CHECK (priority IN ('HIGH', 'MEDIUM', 'LOW')),
    evidence_ids text[] NOT NULL,
    hypothesis text NOT NULL,
    next_check text NOT NULL,
    PRIMARY KEY (run_id, finding_index)
);

CREATE TABLE IF NOT EXISTS decision_intelligence.ai_review_feedback (
    feedback_id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    finding_index integer NOT NULL,
    verdict text NOT NULL CHECK (verdict IN ('ACCEPT', 'REJECT', 'REVISE')),
    reviewer text NOT NULL,
    note text NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (run_id, finding_index)
        REFERENCES decision_intelligence.ai_review_finding(run_id, finding_index)
);

CREATE INDEX IF NOT EXISTS ai_review_feedback_run_idx
    ON decision_intelligence.ai_review_feedback(run_id, finding_index, reviewed_at DESC);

COMMIT;
