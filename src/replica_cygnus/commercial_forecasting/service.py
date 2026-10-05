from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from html import escape
from importlib.metadata import version
import json
from pathlib import Path
import platform
import shutil
import subprocess
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd

from .core import Config, FEATURES, attach_intervals, design, evaluate, fit_predict, validate_panel
from .evaluation import apply_policy, select_policy
from .robustness import diagnostics, outcome_scope, sha256, snapshot_revisions, verify_integrity, write_integrity

SEMANTICS = 'RECONSTRUCTED_REVISED_HISTORY'


def json_safe(value):
    """Strict JSON suitable for PostgreSQL jsonb; no NaN/Infinity."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def dumps(value):
    return json.dumps(json_safe(value), ensure_ascii=False, indent=2, allow_nan=False)


def read_source(conn):
    # Known contract, excluding partial months and prohibited project CAM.
    with conn.cursor() as cur:
        cur.execute('''SELECT periodo_mes,codigo_proyecto,ventas_mes,stock_inicial,
            stock_final,ingresos_mes,unidades_revision
            FROM analytics.v_absorcion_ventas_mensual
            WHERE NOT mes_parcial AND codigo_proyecto <> 'CAM'
            ORDER BY codigo_proyecto,periodo_mes''')
        return pd.DataFrame(cur.fetchall(), columns=['month', 'project', 'sales',
                            'stock_open', 'stock_close', 'inflows', 'review_units'])


def read_review_cases(conn, projects):
    """Read unit/cycle evidence from the local absorption contract; no DB writes."""
    if not projects:
        raise ValueError('Supply at least one project')
    with conn.cursor() as cur:
        cur.execute('''SELECT codigo_proyecto AS project,nombre_proyecto,codigo_unidad,
            nombre_unidad,estado_comercial_actual,fecha_venta,ventas_elegibles,
            ciclos_revision,ultima_actualizacion_ciclos,
            (ventas_elegibles > 1) AS duplicidad_venta_vigente,
            (ciclos_revision > 0) AS ciclo_pendiente,
            (fecha_venta IS NULL AND lower(coalesce(estado_comercial_actual,'')) LIKE '%%vendid%%')
                AS vendida_sin_venta_validada
            FROM analytics.v_absorcion_ventas_revision
            WHERE codigo_proyecto=ANY(%s)
            ORDER BY codigo_proyecto,codigo_unidad''', (projects,))
        unit_columns=[c.name for c in cur.description]
        units=[dict(zip(unit_columns,row)) for row in cur.fetchall()]
        cur.execute('''SELECT u.codigo_proyecto AS project,u.codigo_unidad,
            c.codigo_proyecto AS proyecto_del_ciclo,c.codigo_proforma,c.calidad_ciclo,
            c.metodo_fecha_venta,c.fecha_de_minuta,c.fecha_firma_legacy,
            c.fecha_venta_documental,c.fecha_anulacion,c.reconciliation_status,
            c.observacion
            FROM analytics.v_absorcion_ventas_revision u
            JOIN analytics.v_absorcion_ventas_ciclos c USING (codigo_unidad)
            WHERE u.codigo_proyecto=ANY(%s)
            ORDER BY u.codigo_proyecto,u.codigo_unidad,c.codigo_proforma''', (projects,))
        cycle_columns=[c.name for c in cur.description]
        cycles=[dict(zip(cycle_columns,row)) for row in cur.fetchall()]
    return dict(projects=projects, distinct_review_units=len(units), units=units,
                cycles=cycles, source='LIVE_LOCAL_ABSORPTION_VIEWS')


def ensure_schema(conn, root):
    with conn.cursor() as cur:
        for relative in ('01_evidence.sql', '02_monthly_projection.sql'):
            cur.execute((root/'sql/97_commercial_forecasting'/relative).read_text(encoding='utf-8'))


def save_snapshot(conn, panel, quality):
    snapshot_id = str(uuid4())
    from psycopg.types.json import Jsonb
    with conn.cursor() as cur:
        cur.execute('''SELECT snapshot_id,panel FROM features.commercial_forecast_snapshots
                       ORDER BY captured_at DESC,snapshot_id DESC LIMIT 1''')
        previous = cur.fetchone()
        quality['snapshot_comparison'] = (dict(previous_snapshot_id=str(previous[0]),
            **snapshot_revisions(pd.DataFrame(previous[1]), panel)) if previous else
            dict(previous_snapshot_id=None, status='FIRST_CAPTURE'))
        cur.execute('''INSERT INTO features.commercial_forecast_snapshots
            (snapshot_id,complete_through,source_semantics,data_sha256,panel,quality)
            VALUES (%s,%s,%s,%s,%s,%s)''', (snapshot_id, panel.month.max().date(), SEMANTICS,
            quality['sha256'], Jsonb(json_safe(panel.to_dict('records'))), Jsonb(json_safe(quality))))
    return snapshot_id


def execute(panel, root: Path, output: Path, cfg: Config, *, synthetic=False, snapshot_id=None, snapshot_context=None):
    clean, quality = validate_panel(panel)
    if snapshot_context:
        quality['snapshot_comparison'] = snapshot_context
    bt, summary, evidence, selected = evaluate(clean, cfg)
    origin = clean.month.max()
    future, final_fit, bundles = fit_predict(clean, origin, cfg)
    if future.empty:
        raise ValueError('No current eligible project forecasts; inspect quality report')
    future = attach_intervals(future, bt, cfg)
    policy = select_policy(bt, cfg)
    future = apply_policy(future, policy, cfg.horizon)
    future['monthly_increment'] = future.groupby(['project', 'model']).prediction.diff().fillna(future.prediction)
    run_id = str(uuid4())
    directory = output/run_id
    directory.mkdir(parents=True, exist_ok=False)
    robust, coverage, paired, policy_rows, calibration = diagnostics(clean, future, bt, cfg, policy)
    created = datetime.now(timezone.utc)
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit, dirty = None, None
    manifest = dict(run_id=run_id, snapshot_id=snapshot_id, created_at=created.isoformat(),
        source_semantics='SYNTHETIC_DEMO' if synthetic else SEMANTICS,
        evidence_level='SYNTHETIC_ONLY' if synthetic else 'HISTORICAL_DIAGNOSTIC_SHADOW',
        deployment_status='SHADOW_NO_AUTOMATIC_PROMOTION', selected_model=selected,
        selected_on='complete validation paths, project guards, identical baseline/fallback population; no test selection',
        config=asdict(cfg), data_quality=quality, git_commit=commit, git_dirty=dirty,
        libraries={p: version(p) for p in ('numpy', 'pandas', 'scikit-learn', 'statsmodels', 'scipy', 'joblib')},
        python=platform.python_version(), architecture_version='2.0',
        selection_policy=policy, robustness=robust, coverage_projects=coverage.to_dict('records'),
        features=FEATURES, origin=str(origin.date()), final_training=final_fit,
        limitations=['Historical source revised retrospectively: not point-in-time backtest',
            'Existing inventory scenario: no additions, reinstatements or other exits',
            'No causal discount elasticity and no cash collection forecast',
            'Empirical error intervals: temporal dependence may alter nominal coverage',
            'Forecast window starts after origin; issuance may occur after window start',
            'Cluster IDs local to each training run; no stable regime names asserted'])
    # A dirty commit alone is not reproducible: preserve the actual forecasting source bytes.
    code_paths = [*sorted((root/'src/replica_cygnus/commercial_forecasting').glob('*.py')),
                  root/'scripts/commercial_forecasting.py', root/'sql/97_commercial_forecasting/01_evidence.sql',
                  root/'pyproject.toml']
    manifest['source_files'] = {}
    for source in code_paths:
        relative = source.relative_to(root)
        target = directory/'source_code'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest['source_files'][relative.as_posix()] = sha256(target)
    clean.to_csv(directory/'panel.csv', index=False)
    design(clean, cfg).to_csv(directory/'features.csv', index=False)
    bt.to_csv(directory/'backtest.csv', index=False)
    summary.to_csv(directory/'metrics.csv', index=False)
    future.to_csv(directory/'predictions.csv', index=False)
    (directory/'quality.json').write_text(dumps(quality), encoding='utf-8')
    (directory/'manifest.json').write_text(dumps(manifest), encoding='utf-8')
    (directory/'training_cuts.json').write_text(dumps(evidence), encoding='utf-8')
    # Persist fitted estimators, transforms and rates for reproducibility, not just metrics.
    joblib.dump(bundles, directory/'trained_models.joblib')
    (directory/'model_profiles.json').write_text(dumps(final_fit), encoding='utf-8')
    coverage.to_csv(directory/'project_coverage.csv', index=False)
    paired.to_csv(directory/'paired_comparisons.csv', index=False)
    policy_rows.to_csv(directory/'policy_backtest.csv', index=False)
    calibration.to_csv(directory/'interval_calibration.csv', index=False)
    (directory/'selection_policy.json').write_text(dumps(policy), encoding='utf-8')
    (directory/'robustness.json').write_text(dumps(robust), encoding='utf-8')
    selected_rows = future[future.is_selected].copy()
    tables = [('Cobertura: cada proyecto tiene un estado explícito', coverage),
              ('Prueba final: candidatos sobre los mismos casos que su referencia', paired[paired.partition.eq('test') & paired.horizon.eq(0)] if len(paired) else paired),
              ('Predicciones acumuladas por horizonte', selected_rows),
              ('Evaluación: validación y prueba final separadas', summary),
              ('Detalle de modelos entrenados', pd.DataFrame(final_fit.get('clusters', [])))]
    body = ''.join(f'<h2>{escape(title)}</h2>{table.to_html(index=False, escape=True, na_rep="Sin evidencia suficiente")}'
                   for title, table in tables)
    html = f'''<!doctype html><html lang="es"><meta charset="utf-8"><title>Cygnus — Evidencia forecasting</title>
<style>body{{font:16px system-ui;margin:40px;color:#163047}}table{{border-collapse:collapse;font-size:13px;display:block;overflow:auto}}td,th{{padding:9px;border-bottom:1px solid #ddd}}th{{background:#e8f1f5}}.status{{padding:18px;background:#fff1cc}}h1{{color:#123b55}}</style>
<h1>Cygnus · Forecasting comercial</h1><p>Corte: {origin.date()} · Ejecución: {run_id}</p>
<p class="status">{escape(manifest['evidence_level'])}. Seguimiento sin promoción automática.
Los resultados históricos reconstruidos no certifican predicción con información disponible en el pasado.</p>
<p>Modelo seleccionado en validación: <b>{escape(selected)}</b>. Ventas acumuladas de departamentos del stock actual.
No sumar horizontes 1, 3 y 6: se superponen. Las bandas vacías indican falta de errores anteriores maduros.</p>
<p>Cobertura: {robust['projects_forecast']} de {robust['projects_total']} proyectos;
stock cubierto {robust['stock_forecast']:g} de {robust['stock_total']:g}.
Evidencia temporal de prueba: {escape(robust['test_temporal_uncertainty']['status'])}.
Los modelos se comparan con fallback incluido en policy_backtest.csv. Los cortes solapados no son ensayos independientes.</p>
{body}<h2>Qué aporta la inteligencia</h2><p>Aprende patrones de absorción y oferta; reconoce estados similares;
compara sus predicciones con alternativas y conserva evidencia. Las alertas de brecha requieren metas registradas.
Las asociaciones no demuestran efectos causales ni recaudación.</p></html>'''
    (directory/'report.html').write_text(html, encoding='utf-8')
    write_integrity(directory)
    return directory, manifest, future, bt


def store_run(conn, directory, manifest, future, backtest):
    from psycopg.types.json import Jsonb
    with conn.cursor() as cur:
        cur.execute('''INSERT INTO model_control.commercial_forecast_runs
            (run_id,snapshot_id,manifest,selected_model,evidence_level,artifact_path)
            VALUES (%s,%s,%s,%s,%s,%s)''', (manifest['run_id'], manifest['snapshot_id'],
            Jsonb(json_safe(manifest)), manifest['selected_model'], manifest['evidence_level'], str(directory)))
        for _, r in future.iterrows():
            cur.execute('''INSERT INTO analytics.commercial_forecast_predictions
                (run_id,project,origin,horizon,model,prediction,stock,lower80,upper80,lower95,upper95,
                 is_selected,state_probabilities) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (manifest['run_id'], r.project, r.origin.date(), int(r.horizon), r.model,
                 float(r.prediction), float(r.stock), *[json_safe(r[k]) for k in ('lower80','upper80','lower95','upper95')],
                 bool(r.is_selected), Jsonb(json.loads(r.state_probabilities)) if r.state_probabilities else None))
        for _, r in backtest.iterrows():
            cur.execute('''INSERT INTO analytics.commercial_forecast_backtest
                (run_id,project,origin,horizon,model,partition,actual,prediction,lower80,upper80,lower95,upper95)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (manifest['run_id'], r.project, r.origin.date(), int(r.horizon), r.model, r.partition,
                 float(r.actual), float(r.prediction), *[json_safe(r[k]) for k in ('lower80','upper80','lower95','upper95')]))


def measure(conn):
    """First mature snapshot freezes outcome; later revisions never rewrite it."""
    with conn.cursor() as cur:
        cur.execute('''SELECT p.run_id,p.project,p.horizon,p.model,p.origin,p.stock,r.created_at
          FROM analytics.commercial_forecast_predictions p
          JOIN model_control.commercial_forecast_runs r USING(run_id)
          LEFT JOIN analytics.commercial_forecast_outcomes o USING(run_id,project,horizon,model)
          WHERE o.run_id IS NULL''')
        pending = cur.fetchall()
        count = 0
        for run_id, project, h, model, origin, stock, created in pending:
            end = pd.Timestamp(origin)+pd.DateOffset(months=h)
            cur.execute('''SELECT snapshot_id,panel FROM features.commercial_forecast_snapshots
                WHERE complete_through >= %s AND captured_at > %s
                ORDER BY captured_at,snapshot_id''', (end.date(), created))
            selected_snapshot, assessed = None, None
            for snapshot in cur.fetchall():
                panel = pd.DataFrame(snapshot[1]); panel['month'] = pd.to_datetime(panel.month)
                window = panel[panel.project.eq(project) & panel.month.gt(pd.Timestamp(origin)) & panel.month.le(end)]
                result = outcome_scope(window, origin, h, stock)
                if result['complete']:
                    selected_snapshot, assessed = snapshot[0], result
                    break
            if selected_snapshot is None:
                continue
            cur.execute('''INSERT INTO analytics.commercial_forecast_outcomes
              (run_id,project,horizon,model,outcome_snapshot_id,actual,eligible_scope,eligibility_reason)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
              (run_id, project, h, model, selected_snapshot, assessed['actual'], assessed['eligible_scope'], assessed['reason']))
            count += cur.rowcount
    return count


def audit_artifacts(source: Path, output: Path):
    """Audit old runs without loading joblib, refitting models or rewriting evidence."""
    integrity = verify_integrity(source)
    if integrity['status'] == 'FAILED':
        raise ValueError('Artifact integrity failed; preserve and investigate the original evidence')
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    cfg = Config(**manifest['config'])
    cfg.validate()
    panel, _ = validate_panel(pd.read_csv(source/'panel.csv', dtype={'project': str}))
    bt = pd.read_csv(source/'backtest.csv', dtype={'project': str}, parse_dates=['origin', 'outcome_month'])
    future = pd.read_csv(source/'predictions.csv', dtype={'project': str}, parse_dates=['origin'])
    policy = select_policy(bt, cfg)
    robust, coverage, paired, policy_rows, calibration = diagnostics(panel, future, bt, cfg, policy)
    robust['audit_only'] = True
    robust['original_selected_model'] = manifest['selected_model']
    robust['source_integrity'] = integrity
    robust['input_sha256'] = {name: sha256(source/name) for name in ('panel.csv', 'backtest.csv', 'predictions.csv', 'manifest.json')}
    robust['source_run_id'] = manifest['run_id']
    directory = output/str(uuid4()); directory.mkdir(parents=True, exist_ok=False)
    for name, frame in [('project_coverage', coverage), ('paired_comparisons', paired),
                        ('policy_backtest', policy_rows), ('interval_calibration', calibration)]:
        frame.to_csv(directory/f'{name}.csv', index=False)
    (directory/'robustness.json').write_text(dumps(robust), encoding='utf-8')
    (directory/'selection_policy.json').write_text(dumps(policy), encoding='utf-8')
    comparable = paired[paired.partition.eq('test') & paired.horizon.eq(0)] if len(paired) else paired
    comparable = comparable.reindex(columns=['model','rows','projects','origins','mae','baseline_mae','wape','relative_improvement'])
    decisions = pd.DataFrame(policy['project_decisions'])
    reasons = decisions.groupby(['candidate','decision']).size().reset_index(name='projects') if len(decisions) else decisions
    stock_pct = 100 * robust['stock_coverage'] if robust['stock_coverage'] is not None else 0.
    html = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cygnus · Auditoría de robustez</title><style>
body{{font:16px/1.55 system-ui,sans-serif;color:#173447;background:#f1f5f7;margin:0}}
main{{max-width:1180px;margin:35px auto;padding:32px;background:white}}h1,h2{{line-height:1.2}}
.cards{{display:flex;flex-wrap:wrap;gap:16px}}.card{{background:#eaf3f5;padding:20px;flex:1;min-width:210px}}
.card strong{{font-size:30px;display:block}}.note{{background:#fff3d6;border-left:5px solid #b57a12;padding:18px}}
.table{{overflow:auto;margin:18px 0}}table{{border-collapse:collapse;min-width:100%;font-size:13px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #dce4e8}}th{{background:#173447;color:white}}
.track{{background:#dce4e8;height:16px;margin-top:12px}}.fill{{background:#21878d;height:100%}}small{{color:#536d79}}@media print{{main{{margin:0;padding:12px}}.table{{overflow:visible}}}}
</style></head><body><main><small>CYGNUS · FORECASTING COMERCIAL · AUDITORÍA V2</small>
<h1>Qué evidencia respalda el pronóstico</h1><p>Run original: {escape(manifest['run_id'])}. Corte: {escape(manifest['origin'])}.</p>
<div class="cards"><div class="card"><strong>{robust['projects_forecast']} / {robust['projects_total']}</strong>proyectos con pronóstico original</div>
<div class="card"><strong>{stock_pct:.1f}%</strong>del stock del panel cubierto ({robust['stock_forecast']:g} / {robust['stock_total']:g})<div class="track"><div class="fill" style="width:{stock_pct:.1f}%"></div></div></div>
<div class="card"><strong>{robust['test_temporal_uncertainty']['independent_origins']}</strong>cortes de prueba no solapados al horizonte completo</div></div>
<h2>Decisión de las nuevas reglas</h2><p>Selección emitida: <b>{escape(manifest['selected_model'])}</b>.
Política que propondrían los controles v2 sobre la validación disponible: <b>{escape(policy['selected_model'])}</b>.</p>
<p class="note">La auditoría no reentrena ni reemplaza el pronóstico original. Una mejora histórica no demuestra todavía precisión operativa.
El histórico revisado sigue siendo diagnóstico. La cobertura incompleta y los cortes solapados limitan las conclusiones.</p>
<h2>Cobertura del run original</h2><p>Los proyectos en cuarentena conservan una razón visible. Las cantidades pronosticadas son acumuladas hasta el horizonte indicado.</p>
<div class="table">{coverage.to_html(index=False,escape=True,na_rep='Sin pronóstico',float_format=lambda x:f'{x:.2f}')}</div>
<h2>Comparación histórica sobre los mismos casos</h2><p>MAE en unidades por proyecto/origen/horizonte. WAPE y mejora son fracciones; no equivalen a una tasa de acierto. Cada candidato se empareja con la referencia.</p>
<div class="table">{comparable.to_html(index=False,escape=True,na_rep='Sin evidencia',float_format=lambda x:f'{x:.4f}')}</div>
<h2>Por qué se conserva o cambia la referencia por proyecto</h2><div class="table">{reasons.to_html(index=False,escape=True)}</div>
<h2>Prioridades para la siguiente medición</h2><ol><li>Resolver la evidencia de los proyectos en cuarentena sin alterar las reglas canónicas.</li>
<li>Emitir y conservar nuevas versiones; medir resultados cuando cierre cada ventana.</li>
<li>Revisar error, sesgo, cobertura e intervalos por proyecto y horizonte; distinguir emisión antes del inicio y durante la ventana.</li></ol>
<small>Integridad de archivos originales: {escape(integrity['status'])}. Los hashes del análisis y la política completa se conservan en los JSON del mismo directorio.
No se certifican versiones históricas inexistentes ni se promueve automáticamente un modelo.</small></main></body></html>'''
    (directory/'report.html').write_text(html, encoding='utf-8')
    write_integrity(directory)
    return directory, robust


def synthetic_panel(seed=42):
    """Deterministic demo with fictitious project identifiers; never production evidence."""
    rng = np.random.default_rng(seed)
    rows = []
    for n in range(6):
        stock = 1500
        for month in pd.date_range('2023-01-01', periods=42, freq='MS'):
            rate = max(1., 3+n+2*np.sin(2*np.pi*month.month/12)+.08*(month.year-2023)*12)
            sales = min(stock, int(rng.poisson(rate)))
            rows.append(dict(month=month, project=f'DEMO_{n+1}', sales=sales,
                             stock_open=stock, stock_close=stock-sales, inflows=0, review_units=0))
            stock -= sales
    return pd.DataFrame(rows)
