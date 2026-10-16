BEGIN;

-- Cover the prediction FK independently from the decision-first unique index.
-- This keeps joins/deletes from ml.decision_model_predictions efficient.
CREATE INDEX IF NOT EXISTS ix_decision_model_links_prediction_id
    ON decision_intelligence.decision_model_links(prediction_id)
    WHERE prediction_id IS NOT NULL;

COMMIT;
