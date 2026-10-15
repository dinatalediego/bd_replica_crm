-- Opt-in artifact registry. No source loading, scheduling or RAW/CORE mutations.
CREATE SCHEMA IF NOT EXISTS publish;
CREATE TABLE IF NOT EXISTS publish.product_release (
 archive_sha256 text PRIMARY KEY CHECK(archive_sha256 ~ '^[a-f0-9]{64}$'),
 product_id text NOT NULL,
 product_version text NOT NULL,
 classification text NOT NULL CHECK(classification IN ('PRIVATE','SYNTHETIC')),
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 manifest jsonb NOT NULL CHECK(jsonb_typeof(manifest)='object'),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
 CHECK(manifest->>'classification'=classification)
);
CREATE OR REPLACE FUNCTION publish.reject_release_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Published evidence is immutable; register a new artifact'; END;
$$;
DROP TRIGGER IF EXISTS release_append_only ON publish.product_release;
CREATE TRIGGER release_append_only BEFORE UPDATE OR DELETE ON publish.product_release
FOR EACH ROW EXECUTE FUNCTION publish.reject_release_mutation();
DROP TRIGGER IF EXISTS release_no_truncate ON publish.product_release;
CREATE TRIGGER release_no_truncate BEFORE TRUNCATE ON publish.product_release
FOR EACH STATEMENT EXECUTE FUNCTION publish.reject_release_mutation();
CREATE OR REPLACE VIEW publish.data_product AS
SELECT archive_sha256,product_id,product_version,classification,registered_at,
 payload->'data' AS data_product FROM publish.product_release;
CREATE OR REPLACE VIEW publish.model_run AS
SELECT archive_sha256,payload->'model' AS model_product FROM publish.product_release;
CREATE OR REPLACE VIEW publish.indicator AS
SELECT r.archive_sha256,r.classification,x.value AS indicator
FROM publish.product_release r CROSS JOIN LATERAL jsonb_array_elements(r.payload->'data'->'indicators') x;
CREATE OR REPLACE VIEW publish.model_metric AS
SELECT r.archive_sha256,x.value AS metric
FROM publish.product_release r CROSS JOIN LATERAL jsonb_array_elements(r.payload->'model'->'metrics') x;
CREATE OR REPLACE VIEW publish.model_prediction AS
SELECT r.archive_sha256,x.value AS prediction
FROM publish.product_release r CROSS JOIN LATERAL jsonb_array_elements(r.payload->'model'->'results') x;
CREATE OR REPLACE VIEW publish.scenario AS
SELECT r.archive_sha256,x.value AS scenario
FROM publish.product_release r CROSS JOIN LATERAL jsonb_array_elements(r.payload->'scenario'->'scenarios') x;
CREATE OR REPLACE VIEW publish.finding AS
SELECT r.archive_sha256,x.value AS finding
FROM publish.product_release r CROSS JOIN LATERAL jsonb_array_elements(r.payload->'story'->'findings') x;
CREATE OR REPLACE VIEW publish.numeric_story AS
SELECT archive_sha256,payload->'story' AS story FROM publish.product_release;
CREATE OR REPLACE VIEW publish.decision_insight AS
SELECT r.archive_sha256,x.value AS decision
FROM publish.product_release r CROSS JOIN LATERAL jsonb_array_elements(r.payload->'story'->'decisions') x;
CREATE OR REPLACE VIEW publish.wisdom_card AS
SELECT r.archive_sha256,x.value AS wisdom_card
FROM publish.product_release r CROSS JOIN LATERAL jsonb_array_elements(r.payload->'story'->'wisdom_cards') x;
-- Views inherit DB permissions. SYNTHETIC label is NOT a publication approval.
-- Never grant anonymous access to this schema: PRIVATE releases coexist here.
REVOKE ALL ON SCHEMA publish FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA publish FROM PUBLIC;

CREATE TABLE IF NOT EXISTS publish.decision_event (
 event_sha256 text PRIMARY KEY CHECK(event_sha256 ~ '^[a-f0-9]{64}$'),
 archive_sha256 text NOT NULL REFERENCES publish.product_release,
 decision_id text NOT NULL,
 event_type text NOT NULL CHECK(event_type IN ('ACTION_RECORDED','OUTCOME_OBSERVED')),
 occurred_at timestamptz NOT NULL,
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE OR REPLACE FUNCTION publish.check_decision_reference()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (
   SELECT 1 FROM publish.product_release r,
   LATERAL jsonb_array_elements(r.payload->'story'->'decisions') d
   WHERE r.archive_sha256=NEW.archive_sha256 AND d->>'id'=NEW.decision_id
 ) THEN RAISE EXCEPTION 'Decision must belong to the referenced release'; END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS decision_reference ON publish.decision_event;
CREATE TRIGGER decision_reference BEFORE INSERT ON publish.decision_event
FOR EACH ROW EXECUTE FUNCTION publish.check_decision_reference();
DROP TRIGGER IF EXISTS decision_event_append_only ON publish.decision_event;
CREATE TRIGGER decision_event_append_only BEFORE UPDATE OR DELETE ON publish.decision_event
FOR EACH ROW EXECUTE FUNCTION publish.reject_release_mutation();
DROP TRIGGER IF EXISTS decision_event_no_truncate ON publish.decision_event;
CREATE TRIGGER decision_event_no_truncate BEFORE TRUNCATE ON publish.decision_event
FOR EACH STATEMENT EXECUTE FUNCTION publish.reject_release_mutation();
CREATE OR REPLACE VIEW publish.decision_learning AS
SELECT d.archive_sha256,d.decision->>'id' AS decision_id,
       e.event_type,e.occurred_at,e.payload AS event,
       'Outcome association is not causal identification'::text AS limitation
FROM publish.decision_insight d LEFT JOIN publish.decision_event e
 ON e.archive_sha256=d.archive_sha256 AND e.decision_id=d.decision->>'id';
REVOKE ALL ON ALL TABLES IN SCHEMA publish FROM PUBLIC;
