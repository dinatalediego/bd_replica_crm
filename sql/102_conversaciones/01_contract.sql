-- Local-only, append-only conversation evidence. All timestamps are America/Lima wall time.
CREATE SCHEMA IF NOT EXISTS raw_conversations;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS etl_control;

REVOKE ALL ON SCHEMA raw_conversations FROM PUBLIC;

CREATE TABLE IF NOT EXISTS etl_control.conversation_sources (
    source_id bigserial PRIMARY KEY,
    source_name text NOT NULL UNIQUE,
    last_file_sha256 char(64),
    message_count integer NOT NULL DEFAULT 0 CHECK (message_count >= 0),
    current_ruleset_version integer NOT NULL DEFAULT 0,
    last_run_id bigint,
    last_success_at timestamptz
);
CREATE TABLE IF NOT EXISTS etl_control.conversation_import_runs (
    run_id bigserial PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES etl_control.conversation_sources(source_id),
    file_sha256 char(64) NOT NULL,
    parsed_messages integer NOT NULL,
    new_messages integer NOT NULL,
    new_events integer NOT NULL,
    ruleset_version integer NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_conversation_runs_source
    ON etl_control.conversation_import_runs(source_id, run_id DESC);

CREATE TABLE IF NOT EXISTS raw_conversations.messages (
    message_id char(64) PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES etl_control.conversation_sources(source_id),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    sent_at timestamp NOT NULL,
    sender text,
    body text NOT NULL,
    source_line integer NOT NULL,
    raw_message text NOT NULL,
    is_multimedia boolean NOT NULL,
    first_run_id bigint NOT NULL REFERENCES etl_control.conversation_import_runs(run_id),
    inserted_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, ordinal)
);
CREATE INDEX IF NOT EXISTS ix_conversation_messages_time
    ON raw_conversations.messages(source_id, sent_at);
REVOKE ALL ON ALL TABLES IN SCHEMA raw_conversations FROM PUBLIC;

CREATE TABLE IF NOT EXISTS analytics.conversation_events (
    event_id char(64) PRIMARY KEY,
    message_id char(64) NOT NULL REFERENCES raw_conversations.messages(message_id),
    source_id bigint NOT NULL REFERENCES etl_control.conversation_sources(source_id),
    event_index smallint NOT NULL,
    ruleset_version integer NOT NULL,
    event_type text NOT NULL,
    reported_date date NOT NULL,
    project_name text,
    venue_type text CHECK (venue_type IN ('feria','sala','sala_inferida')),
    count_min integer CHECK (count_min >= 0),
    count_max integer CHECK (count_max >= count_min),
    confidence text NOT NULL CHECK (confidence IN ('media','baja')),
    review_required boolean NOT NULL,
    note text NOT NULL,
    first_run_id bigint NOT NULL REFERENCES etl_control.conversation_import_runs(run_id),
    inserted_at timestamptz NOT NULL DEFAULT now(),
    unit_code text,
    related_event_id char(64),
    UNIQUE (message_id, ruleset_version, event_index)
);
-- The contract was installed before contextual event linking on some PCs.
ALTER TABLE analytics.conversation_events ADD COLUMN IF NOT EXISTS unit_code text;
ALTER TABLE analytics.conversation_events ADD COLUMN IF NOT EXISTS related_event_id char(64);
CREATE INDEX IF NOT EXISTS ix_conversation_events_type_date
    ON analytics.conversation_events(source_id, event_type, reported_date);
CREATE INDEX IF NOT EXISTS ix_conversation_events_review
    ON analytics.conversation_events(source_id, review_required, reported_date);
CREATE INDEX IF NOT EXISTS ix_conversation_events_related
    ON analytics.conversation_events(related_event_id) WHERE related_event_id IS NOT NULL;

CREATE OR REPLACE FUNCTION etl_control.protect_conversation_evidence()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'La evidencia de conversaciones es inmutable; crear una nueva versión de reglas';
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='conversation_evidence_immutable'
                   AND tgrelid='raw_conversations.messages'::regclass) THEN
        CREATE TRIGGER conversation_evidence_immutable BEFORE UPDATE OR DELETE
        ON raw_conversations.messages FOR EACH ROW EXECUTE FUNCTION etl_control.protect_conversation_evidence();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='conversation_evidence_immutable'
                   AND tgrelid='analytics.conversation_events'::regclass) THEN
        CREATE TRIGGER conversation_evidence_immutable BEFORE UPDATE OR DELETE
        ON analytics.conversation_events FOR EACH ROW EXECUTE FUNCTION etl_control.protect_conversation_evidence();
    END IF;
END $$;

CREATE OR REPLACE VIEW analytics.v_conversation_events_current AS
SELECT e.event_id, e.message_id, e.source_id, e.event_index, e.ruleset_version,
       e.event_type, e.reported_date, e.project_name, e.venue_type, e.count_min,
       e.count_max, e.confidence, e.review_required, e.note, e.first_run_id,
       e.inserted_at, m.sent_at AS message_at, m.sender, m.source_line,
       m.is_multimedia, e.unit_code, e.related_event_id
FROM analytics.conversation_events e
JOIN etl_control.conversation_sources s ON s.source_id=e.source_id
JOIN raw_conversations.messages m ON m.message_id=e.message_id
WHERE e.ruleset_version=s.current_ruleset_version;

CREATE OR REPLACE VIEW analytics.v_conversation_visit_reports AS
SELECT event_id, message_id, source_id, message_at, reported_date,
       project_name, venue_type, count_min, count_max, confidence,
       review_required, note, sender, source_line
FROM analytics.v_conversation_events_current
WHERE event_type='visita_reporte';

-- These are sums of explicit reports, not CRM-verified unique visitors.
CREATE OR REPLACE VIEW analytics.v_conversation_visits_daily AS
SELECT source_id, reported_date, project_name, venue_type,
       count(*) AS reports,
       sum(count_min) AS reported_visits_min,
       sum(count_max) AS reported_visits_max,
       count(*) FILTER (WHERE review_required) AS reports_for_review,
       count(*) > 1 AS potential_overlap
FROM analytics.v_conversation_visit_reports
GROUP BY source_id, reported_date, project_name, venue_type;

CREATE OR REPLACE VIEW analytics.v_conversation_project_hourly AS
SELECT source_id, date_trunc('hour',message_at) AS message_hour, project_name,
       count(*) FILTER (WHERE event_type='separacion_anuncio') AS separation_announcements,
       count(*) FILTER (WHERE event_type='cita_reporte') AS appointment_reports,
       count(*) FILTER (WHERE event_type='visita_reporte') AS visit_reports,
       sum(count_min) FILTER (WHERE event_type='visita_reporte') AS reported_visits_min,
       sum(count_max) FILTER (WHERE event_type='visita_reporte') AS reported_visits_max,
       count(*) FILTER (WHERE event_type='bloqueo_stock') AS stock_blocks,
       count(*) FILTER (WHERE event_type='incidencia_crm') AS crm_incidents,
       count(*) FILTER (WHERE event_type='salida_sala') AS room_close_reports
FROM analytics.v_conversation_events_current
GROUP BY source_id, date_trunc('hour',message_at), project_name;

CREATE OR REPLACE VIEW analytics.v_conversation_project_day_signals AS
SELECT source_id, reported_date, project_name,
       count(*) FILTER (WHERE event_type='separacion_anuncio') AS separation_announcements,
       count(*) FILTER (WHERE event_type='minuta_reporte') AS minute_reports,
       count(*) FILTER (WHERE event_type='pago_inicial_reporte') AS initial_payment_reports,
       count(*) FILTER (WHERE event_type='cita_reporte') AS appointment_reports,
       count(*) FILTER (WHERE event_type='visita_reporte') AS visit_reports,
       sum(count_min) FILTER (WHERE event_type='visita_reporte') AS reported_visits_min,
       sum(count_max) FILTER (WHERE event_type='visita_reporte') AS reported_visits_max,
       count(*) FILTER (WHERE event_type='salida_sala') AS room_close_reports,
       count(*) FILTER (WHERE event_type='actividad_feria') AS fair_mentions,
       count(*) FILTER (WHERE event_type='bloqueo_stock') AS stock_blocks,
       count(*) FILTER (WHERE event_type='incidencia_crm') AS crm_incidents,
       count(*) FILTER (WHERE event_type='celebracion') AS reactions
FROM analytics.v_conversation_events_current
GROUP BY source_id, reported_date, project_name;

CREATE OR REPLACE VIEW analytics.v_conversation_daily_rhythm AS
SELECT source_id, sent_at::date AS message_date, extract(hour from sent_at)::integer AS hour_of_day,
       count(*) AS messages, count(DISTINCT sender) AS participants,
       count(*) FILTER (WHERE is_multimedia) AS multimedia_messages
FROM raw_conversations.messages
GROUP BY source_id, sent_at::date, extract(hour from sent_at);

-- Only contextual reactions linked to a preceding announcement are counted.
-- The initial columns retain the previous Power BI contract.
CREATE OR REPLACE VIEW analytics.v_conversation_sale_reactions AS
SELECT e.event_id, e.message_at AS announcement_at, e.project_name,
       count(r.message_id) FILTER (WHERE r.message_at <= e.message_at + interval '15 minutes') AS reactions_15m,
       count(DISTINCT r.sender) FILTER (WHERE r.message_at <= e.message_at + interval '15 minutes') AS distinct_reactors_15m,
       min(extract(epoch from (r.message_at-e.message_at))/60.0) AS first_reaction_minutes,
       count(r.message_id) AS reactions_24h,
       count(DISTINCT r.sender) AS distinct_reactors_24h,
       e.unit_code, e.source_id
FROM analytics.v_conversation_events_current e
LEFT JOIN analytics.v_conversation_events_current r
    ON r.related_event_id=e.event_id AND r.event_type='celebracion'
WHERE e.event_type='separacion_anuncio'
GROUP BY e.event_id,e.message_at,e.project_name,e.unit_code,e.source_id;
