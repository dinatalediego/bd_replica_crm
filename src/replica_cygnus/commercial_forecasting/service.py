from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd

from .core import Config, FEATURES, attach_intervals, design, evaluate, fit_predict, validate_panel

SEMANTICS = 'RECONSTRUCTED_REVISED_HISTORY'


def json_safe(value):
    """Strict JSON suitable for PostgreSQL jsonb; no NaN/Infinity."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
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


def ensure_schema(conn, root):
    with conn.cursor() as cur:
        cur.execute((root/'sql/97_commercial_forecasting/01_evidence.sql').read_text(encoding='utf-8'))


def save_snapshot(conn, panel, quality):
    snapshot_id = str(uuid4())
    from psycopg.types.json import Jsonb
    with conn.cursor() as cur:
        cur.execute('''INSERT INTO features.commercial_forecast_snapshots
            (snapshot_id,complete_through,source_semantics,data_sha256,panel,quality)
            VALUES (%s,%s,%s,%s,%s,%s)''', (snapshot_id, panel.month.max().date(), SEMANTICS,
            quality['sha256'], Jsonb(json_safe(panel.to_dict('records'))), Jsonb(json_safe(quality))))
    return snapshot_id


def execute(panel, root: Path, output: Path, cfg: Config, *, synthetic=False, snapshot_id=None):
    clean, quality = validate_panel(panel)
    bt, summary, evidence, selected = evaluate(clean, cfg)
    origin = clean.month.max()
    future, final_fit, bundles = fit_predict(clean, origin, cfg)
    if future.empty:
        raise ValueError('No current eligible project forecasts; inspect quality report')
    future = attach_intervals(future, bt, cfg)
    # Candidate may not be available for new/zero-inventory projects: transparent baseline fallback.
    future['is_selected'] = future.model.eq(selected)
    for project, g in future.groupby('project'):
        if not g.is_selected.any():
            future.loc[g.index, 'is_selected'] = g.model.eq('mean3')
    future['monthly_increment'] = future.groupby(['project', 'model']).prediction.diff().fillna(future.prediction)
    future['selection_reason'] = np.where(future.model.eq(selected), 'VALIDATION_SELECTION',
                                         np.where(future.is_selected, 'PROJECT_BASELINE_FALLBACK', 'SHADOW_CANDIDATE'))
    run_id = str(uuid4())
    directory = output/run_id
    directory.mkdir(parents=True, exist_ok=False)
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
        selected_on='validation paired MAE; final test not used for selection',
        config=asdict(cfg), data_quality=quality, git_commit=commit, git_dirty=dirty,
        libraries={p: version(p) for p in ('numpy', 'pandas', 'scikit-learn', 'statsmodels')},
        features=FEATURES, origin=str(origin.date()), final_training=final_fit,
        limitations=['Historical source revised retrospectively: not point-in-time backtest',
            'Existing inventory scenario: no additions, reinstatements or other exits',
            'No causal discount elasticity and no cash collection forecast',
            'Empirical error intervals: temporal dependence may alter nominal coverage',
            'Forecast window starts after origin; issuance may occur after window start',
            'Cluster IDs local to each training run; no stable regime names asserted'])
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
    selected_rows = future[future.is_selected].copy()
    tables = [('Predicciones acumuladas por horizonte', selected_rows),
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
{body}<h2>Qué aporta la inteligencia</h2><p>Aprende patrones de absorción y oferta; reconoce estados similares;
compara sus predicciones con alternativas y conserva evidencia. Las alertas de brecha requieren metas registradas.
Las asociaciones no demuestran efectos causales ni recaudación.</p></html>'''
    (directory/'report.html').write_text(html, encoding='utf-8')
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
                ORDER BY captured_at,snapshot_id LIMIT 1''', (end.date(), created))
            snapshot = cur.fetchone()
            if snapshot is None:
                continue
            panel = pd.DataFrame(snapshot[1]); panel['month'] = pd.to_datetime(panel.month)
            window = panel[panel.project.eq(project) & panel.month.gt(pd.Timestamp(origin)) & panel.month.le(end)]
            if len(window) != h:
                continue
            eligible = bool(window.inflows.sum()==0 and window.review_units.sum()==0 and window.sales.sum() <= float(stock))
            cur.execute('''INSERT INTO analytics.commercial_forecast_outcomes
              (run_id,project,horizon,model,outcome_snapshot_id,actual,eligible_scope)
              VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
              (run_id, project, h, model, snapshot[0], float(window.sales.sum()), eligible))
            count += cur.rowcount
    return count


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
