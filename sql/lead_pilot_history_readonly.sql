-- SELECT only. Parameters: start_at inclusive, end_at exclusive, end_day (Lima).
-- Rank across ALL available history before filtering the reporting window.
WITH history AS MATERIALIZED (
 SELECT evidence_key,decision_at,captured_at,
        (decision_at AT TIME ZONE 'America/Lima')::date AS day,
        btrim(documento_cliente) AS document,btrim(codigo_proyecto) AS project,
        evidence_source,separacion_14d,minuta_60d,labels_as_of
 FROM features.lead_evidence WHERE decision_at < %(end_at)s
), valid AS (
 SELECT *,row_number() OVER (PARTITION BY document,project ORDER BY decision_at,evidence_key) AS project_order,
          row_number() OVER (PARTITION BY document ORDER BY decision_at,evidence_key) AS global_order
 FROM history WHERE document IS NOT NULL AND document<>'' AND project IS NOT NULL AND project<>''
), daily AS (
 SELECT project,day,count(*) AS assignments,
 count(*) FILTER (WHERE project_order=1) AS first_client_project,
 count(*) FILTER (WHERE global_order=1) AS first_client_global,
 count(*) FILTER (WHERE project_order=1 AND evidence_source='LIVE') AS first_live,
 count(*) FILTER (WHERE project_order=1 AND evidence_source='BACKFILL_INFERRED') AS first_inferred,
 count(*) FILTER (WHERE project_order=1 AND day+14<=%(end_day)s) AS sep_mature,
 count(*) FILTER (WHERE project_order=1 AND day+14<=%(end_day)s
     AND separacion_14d IS NOT NULL AND labels_as_of>=day+14) AS sep_observed,
 count(*) FILTER (WHERE project_order=1 AND day+14<=%(end_day)s
     AND separacion_14d=1 AND labels_as_of>=day+14) AS sep_positive,
 count(*) FILTER (WHERE project_order=1 AND day+60<=%(end_day)s) AS minuta_mature,
 count(*) FILTER (WHERE project_order=1 AND day+60<=%(end_day)s
     AND minuta_60d IS NOT NULL AND labels_as_of>=day+60) AS minuta_observed,
 count(*) FILTER (WHERE project_order=1 AND day+60<=%(end_day)s
     AND minuta_60d=1 AND labels_as_of>=day+60) AS minuta_positive
 FROM valid WHERE decision_at>=%(start_at)s GROUP BY project,day
), quality AS (
 SELECT count(*) AS history_rows,min(decision_at) AS earliest_available,
 max(decision_at) AS latest_decision,max(captured_at) AS latest_capture,max(labels_as_of) AS latest_labels,
 count(*) FILTER (WHERE decision_at>=%(start_at)s) AS window_source_rows,
 count(*) FILTER (WHERE decision_at>=%(start_at)s AND
     (document IS NULL OR document='' OR project IS NULL OR project='')) AS invalid_identity_or_project
 FROM history
)
SELECT jsonb_build_object(
 'quality',(SELECT to_jsonb(q) FROM quality q),
 'daily',coalesce((SELECT jsonb_agg(to_jsonb(d) ORDER BY project,day) FROM daily d),'[]'::jsonb),
 'excluded_at_or_after_cutoff',(SELECT count(*) FROM features.lead_evidence WHERE decision_at>=%(end_at)s)
);
