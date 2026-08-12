-- OPCIONAL: ejecutar solo tras revisar preflight y confirmar que no existe equivalente
CREATE TABLE IF NOT EXISTS observability.absorption_discovery_runs (
 discovery_run_id bigserial PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, status text NOT NULL DEFAULT 'RUNNING', executed_by text NOT NULL DEFAULT current_user, notes text);
CREATE TABLE IF NOT EXISTS observability.absorption_discovery_results (
 discovery_result_id bigserial PRIMARY KEY, discovery_run_id bigint NOT NULL REFERENCES observability.absorption_discovery_runs(discovery_run_id), query_name text NOT NULL, row_number_in_result integer NOT NULL, payload jsonb NOT NULL, captured_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_absorption_discovery_results_run_query ON observability.absorption_discovery_results(discovery_run_id,query_name);
