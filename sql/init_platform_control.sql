-- Cygnus Platform Command Center
-- Readiness operativo de las aplicaciones que sostienen la Jefatura de Inteligencia Comercial.

CREATE SCHEMA IF NOT EXISTS platform_control;

CREATE TABLE IF NOT EXISTS platform_control.application_registry (
    app_key          text PRIMARY KEY,
    app_name         text NOT NULL,
    platform_layer   text NOT NULL,
    owner_role       text NOT NULL,
    environment      text NOT NULL DEFAULT 'planned',
    criticality      text NOT NULL DEFAULT 'medium'
        CHECK (criticality IN ('critical','high','medium','low')),
    weight           numeric(8,2) NOT NULL DEFAULT 1 CHECK (weight > 0),
    enabled          boolean NOT NULL DEFAULT true,
    next_milestone   text,
    next_action      text,
    blocking_reason  text,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS platform_control.readiness_controls (
    control_key       text PRIMARY KEY,
    app_key           text NOT NULL REFERENCES platform_control.application_registry(app_key) ON DELETE CASCADE,
    control_name      text NOT NULL,
    category          text NOT NULL,
    owner_role        text NOT NULL,
    source_type       text NOT NULL DEFAULT 'manual'
        CHECK (source_type IN ('postgres','git','manual','external')),
    status            text NOT NULL DEFAULT 'NOT_STARTED'
        CHECK (status IN ('NOT_STARTED','IN_PROGRESS','BLOCKED','DONE')),
    weight            numeric(8,2) NOT NULL DEFAULT 1 CHECK (weight > 0),
    score             numeric(5,4) GENERATED ALWAYS AS (
        CASE status
            WHEN 'DONE' THEN 1.0
            WHEN 'IN_PROGRESS' THEN 0.5
            WHEN 'BLOCKED' THEN 0.1
            ELSE 0.0
        END
    ) STORED,
    evidence          text,
    details           text,
    last_checked_at   timestamptz,
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_readiness_controls_app
    ON platform_control.readiness_controls (app_key);
CREATE INDEX IF NOT EXISTS ix_readiness_controls_status
    ON platform_control.readiness_controls (status);

CREATE TABLE IF NOT EXISTS platform_control.milestones (
    milestone_key       text PRIMARY KEY,
    milestone_name      text NOT NULL,
    owner_role          text NOT NULL,
    target_date         date,
    status              text NOT NULL DEFAULT 'NOT_STARTED'
        CHECK (status IN ('NOT_STARTED','IN_PROGRESS','BLOCKED','DONE')),
    acceptance_criteria text NOT NULL,
    evidence            text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW platform_control.v_application_readiness AS
SELECT
    a.app_key,
    a.app_name,
    a.platform_layer,
    a.owner_role,
    a.environment,
    a.criticality,
    a.weight,
    a.next_milestone,
    a.next_action,
    a.blocking_reason,
    COUNT(c.control_key) AS controls_total,
    COUNT(*) FILTER (WHERE c.status = 'DONE') AS controls_done,
    COUNT(*) FILTER (WHERE c.status = 'IN_PROGRESS') AS controls_in_progress,
    COUNT(*) FILTER (WHERE c.status = 'BLOCKED') AS controls_blocked,
    COALESCE(
        SUM(c.weight * c.score) / NULLIF(SUM(c.weight), 0),
        0
    )::numeric(6,4) AS readiness_score,
    CASE
        WHEN COUNT(c.control_key) = 0 THEN 'GRAY'
        WHEN COUNT(*) FILTER (WHERE c.status = 'BLOCKED') > 0 THEN 'RED'
        WHEN SUM(c.weight * c.score) / NULLIF(SUM(c.weight), 0) >= 0.80 THEN 'GREEN'
        WHEN SUM(c.weight * c.score) / NULLIF(SUM(c.weight), 0) >= 0.40 THEN 'AMBER'
        ELSE 'GRAY'
    END AS health_status,
    MAX(c.last_checked_at) AS last_checked_at
FROM platform_control.application_registry a
LEFT JOIN platform_control.readiness_controls c USING (app_key)
WHERE a.enabled = true
GROUP BY
    a.app_key, a.app_name, a.platform_layer, a.owner_role, a.environment,
    a.criticality, a.weight, a.next_milestone, a.next_action, a.blocking_reason;

CREATE OR REPLACE VIEW platform_control.v_platform_summary AS
SELECT
    COUNT(*) AS applications,
    ROUND(
        SUM(weight * readiness_score) / NULLIF(SUM(weight), 0),
        4
    ) AS platform_readiness,
    COUNT(*) FILTER (WHERE health_status = 'GREEN') AS apps_green,
    COUNT(*) FILTER (WHERE health_status = 'AMBER') AS apps_amber,
    COUNT(*) FILTER (WHERE health_status = 'RED') AS apps_red,
    COUNT(*) FILTER (WHERE health_status = 'GRAY') AS apps_gray,
    COUNT(*) FILTER (WHERE criticality = 'critical' AND readiness_score < 0.60) AS critical_below_60
FROM platform_control.v_application_readiness;

INSERT INTO platform_control.application_registry
    (app_key, app_name, platform_layer, owner_role, environment, criticality, weight, next_milestone, next_action)
VALUES
    ('postgresql','PostgreSQL','Data Platform','Data Engineering','DEV -> PROD','critical',5,'DW gobernado v1','Cerrar RAW/STAGING/CORE y arquitectura PROD'),
    ('python_etl','Python ETL','Ingesta','Data Engineering','DEV','critical',5,'Pipeline idempotente','Asegurar run_id, reconciliación y manejo de errores'),
    ('dbt','dbt Core','Transformación','Data Engineering','planned','high',4,'Proyecto dbt inicial','Crear proyecto cuando CORE esté estable'),
    ('airflow','Airflow','Orquestación','Data Engineering','planned','high',4,'Primer DAG','Definir runtime del scheduler después del DW mínimo viable'),
    ('github','GitHub','SDLC','Data Engineering','DEV','high',4,'Repositorio gobernado','Mantener secretos fuera del repo y flujo de cambios trazable'),
    ('mlflow','MLflow','ML Governance','Data Science + Data Engineering','planned','high',4,'Tracking DEV','Levantar tracking después de feature layer v1'),
    ('colab','Colab Pro','Experimentación','Data Science','cloud lab','medium',2,'Notebook reusable','Usar GitHub + datasets versionados; no conectar localhost directamente'),
    ('powerbi','Power BI Service','Consumo','BI','PROD','critical',5,'Marts certificados','Migrar reglas críticas de negocio hacia CORE/analytics'),
    ('object_storage','Object Storage','Artifacts','Data Engineering','planned','medium',2,'Artifact store','Elegir S3/Blob/MinIO antes de MLflow productivo'),
    ('prismare','pgvector / Prismare','AI / RAG','Data Science','MVP','medium',2,'Vector store gobernado','Versionar embeddings, metadata y evaluación'),
    ('fastapi','FastAPI','Serving','Data Science + Data Engineering','MVP','medium',2,'Contrato de scoring','Servir únicamente modelos aprobados'),
    ('data_quality','Data Quality','Observabilidad','Data Engineering','DEV','critical',5,'Checks automáticos','Operacionalizar freshness, reconciliación y alertas')
ON CONFLICT (app_key) DO UPDATE SET
    app_name = EXCLUDED.app_name,
    platform_layer = EXCLUDED.platform_layer,
    owner_role = EXCLUDED.owner_role,
    criticality = EXCLUDED.criticality,
    weight = EXCLUDED.weight,
    updated_at = now();

INSERT INTO platform_control.readiness_controls
    (control_key, app_key, control_name, category, owner_role, source_type, status, weight)
VALUES
    ('postgres.schemas','postgresql','Schemas analíticos mínimos','Architecture','Data Engineering','postgres','NOT_STARTED',3),
    ('postgres.observability','postgresql','Capa de observabilidad disponible','Observability','Data Engineering','postgres','NOT_STARTED',2),
    ('postgres.ml_governance','postgresql','Schemas de ML governance disponibles','Governance','Data Engineering','postgres','NOT_STARTED',2),
    ('postgres.decision_layer','postgresql','Decision Intelligence disponible','Architecture','Data Engineering','postgres','NOT_STARTED',2),
    ('etl.control_table','python_etl','Control de ejecuciones ETL','Observability','Data Engineering','postgres','NOT_STARTED',3),
    ('etl.recent_success','python_etl','Última sincronización exitosa reciente','Reliability','Data Engineering','postgres','NOT_STARTED',3),
    ('etl.package','python_etl','Paquete Python instalable / CLI','SDLC','Data Engineering','git','NOT_STARTED',2),
    ('git.repo','github','Repositorio Git detectado','SDLC','Data Engineering','git','NOT_STARTED',2),
    ('git.secrets','github','Protección de archivos .env','Security','Data Engineering','git','NOT_STARTED',3),
    ('git.tests','github','Suite de tests presente','Quality','Data Engineering','git','NOT_STARTED',2),
    ('git.packaging','github','pyproject.toml presente','SDLC','Data Engineering','git','NOT_STARTED',2),
    ('quality.registry','data_quality','Asset registry disponible','Observability','Data Engineering','postgres','NOT_STARTED',2),
    ('quality.snapshots','data_quality','Snapshots de salud existentes','Observability','Data Engineering','postgres','NOT_STARTED',3),
    ('quality.checks','data_quality','Quality checks persistidos','Quality','Data Engineering','postgres','NOT_STARTED',3),
    ('powerbi.pipeline_view','powerbi','Vista de runs para Control Tower','Serving','BI + Data Engineering','postgres','NOT_STARTED',2),
    ('powerbi.asset_view','powerbi','Vista de salud de activos','Serving','BI + Data Engineering','postgres','NOT_STARTED',2),
    ('mlflow.registry_db','mlflow','Model registry metadata disponible','Governance','Data Science','postgres','NOT_STARTED',2),
    ('fastapi.model_ready','fastapi','Champion productivo disponible','Serving','Data Science','manual','NOT_STARTED',2),
    ('colab.repo_connected','colab','Notebook enlazado a repositorio','SDLC','Data Science','manual','NOT_STARTED',2),
    ('dbt.project','dbt','Proyecto dbt inicializado','Setup','Data Engineering','manual','NOT_STARTED',2),
    ('airflow.runtime','airflow','Runtime Airflow definido','Setup','Data Engineering','manual','NOT_STARTED',2),
    ('object_store.provider','object_storage','Proveedor de artifacts definido','Architecture','Data Engineering','manual','NOT_STARTED',2),
    ('prismare.vector_store','prismare','Vector store gobernado','AI Governance','Data Science','manual','NOT_STARTED',2)
ON CONFLICT (control_key) DO UPDATE SET
    control_name = EXCLUDED.control_name,
    category = EXCLUDED.category,
    owner_role = EXCLUDED.owner_role,
    source_type = EXCLUDED.source_type,
    weight = EXCLUDED.weight,
    updated_at = now();

INSERT INTO platform_control.milestones
    (milestone_key, milestone_name, owner_role, status, acceptance_criteria)
VALUES
    ('M01','DW gobernado v1','Data Engineering','IN_PROGRESS','RAW/STAGING/CORE + control de runs + quality checks mínimos'),
    ('M02','Analytics certificado v1','BI + Data Engineering','NOT_STARTED','Funnel, ventas y stock consumidos desde marts certificados'),
    ('M03','ML Governance v1','Data Science + Data Engineering','NOT_STARTED','Experimento reproducible + registry + artifact store'),
    ('M04','Propensity Minuta champion','Data Science','NOT_STARTED','Champion supera baseline con validación temporal'),
    ('M05','Decision Intelligence productiva','Jefatura IC','NOT_STARTED','Score + motivo + acción disponibles para operación comercial')
ON CONFLICT (milestone_key) DO NOTHING;
