"""Disposable PostgreSQL only; mirrors the existing absorption integration fixture."""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import pandas as pd
import pytest

from replica_cygnus.commercial_forecasting.service import (
    ensure_schema, measure, read_review_cases, save_snapshot, store_run,
)
from replica_cygnus.commercial_forecasting.core import validate_panel

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def db():
    psycopg=pytest.importorskip('psycopg')
    dsn=os.environ.get('ABSORCION_TEST_DSN')
    if not dsn:
        pgserver=pytest.importorskip('pgserver')
        server=pgserver.get_server(tempfile.mkdtemp(prefix='forecast-test-'),cleanup_mode='delete')
        dsn=server.get_uri()
    with psycopg.connect(dsn) as conn:
        # Existing schemas signal an unsafe non-disposable DB: do not drop them.
        conn.execute('CREATE SCHEMA analytics; CREATE SCHEMA features; CREATE SCHEMA model_control; CREATE SCHEMA decision_intelligence')
        ensure_schema(conn,ROOT)
        yield conn
        conn.rollback()


def test_schema_is_idempotent_and_evidence_cannot_be_rewritten(db):
    ensure_schema(db,ROOT)
    panel=pd.DataFrame([dict(month='2026-09-01',project='DEMO',sales=2,stock_open=10,stock_close=8,inflows=0,review_units=0)])
    panel,q=validate_panel(panel)
    snapshot_id=save_snapshot(db,panel,q)
    import psycopg
    with pytest.raises(psycopg.Error,match='append-only'):
        with db.transaction():
            db.execute('UPDATE features.commercial_forecast_snapshots SET data_sha256=%s WHERE snapshot_id=%s',('changed',snapshot_id))
    assert db.execute('SELECT data_sha256 FROM features.commercial_forecast_snapshots').fetchone()[0]==q['sha256']


def test_prediction_action_and_first_mature_outcome_roundtrip(db,tmp_path):
    panel=pd.DataFrame([dict(month='2026-09-01',project='DEMO',sales=2,stock_open=10,stock_close=8,inflows=0,review_units=0)])
    panel,q=validate_panel(panel)
    snapshot_id=save_snapshot(db,panel,q)
    run_id=str(uuid4())
    manifest=dict(run_id=run_id,snapshot_id=snapshot_id,selected_model='mean3',evidence_level='HISTORICAL_DIAGNOSTIC_SHADOW')
    forecast=pd.DataFrame([dict(project='DEMO',origin=pd.Timestamp('2026-09-01'),horizon=1,model='mean3',
        prediction=2.,stock=8.,lower80=1.,upper80=3.,lower95=0.,upper95=4.,is_selected=True,state_probabilities=None)])
    backtest=pd.DataFrame([dict(project='DEMO',origin=pd.Timestamp('2026-08-01'),horizon=1,model='mean3',
        partition='test',actual=2.,prediction=3.,lower80=1.,upper80=4.,lower95=0.,upper95=5.)])
    store_run(db,tmp_path,manifest,forecast,backtest)
    assert db.execute('SELECT count(*) FROM analytics.v_commercial_forecast_current').fetchone()[0]==1
    db.execute('''INSERT INTO decision_intelligence.commercial_forecast_goals
      VALUES ('2026-09-01','DEMO',1,4,'commercial_owner')''')
    assert db.execute('SELECT recommendation,expected_shortfall FROM analytics.v_commercial_forecast_current').fetchone()==('REVISAR_BRECHA_COMERCIAL',2)
    db.execute('''INSERT INTO decision_intelligence.commercial_forecast_actions
      (action_id,run_id,project,horizon,model,owner,action,cost)
      VALUES (%s,%s,'DEMO',1,'mean3','commercial_owner','Review pipeline',0)''',(str(uuid4()),run_id))
    # Incomplete outcomes remain unmeasured.
    assert measure(db)==0
    october=pd.DataFrame([dict(month='2026-10-01',project='DEMO',sales=3,stock_open=8,stock_close=5,inflows=0,review_units=0)])
    matured,q2=validate_panel(pd.concat([panel,october],ignore_index=True))
    first_snapshot=save_snapshot(db,matured,q2)
    assert measure(db)==1
    row=db.execute('SELECT actual,error,eligible_scope,outcome_snapshot_id FROM analytics.v_commercial_forecast_performance').fetchone()
    assert row[:3]==(3,-1,True) and str(row[3])==first_snapshot
    # A subsequent historical revision cannot replace the first observed outcome.
    revised=matured.copy(); revised.loc[1,'sales']=4; revised.loc[1,'stock_close']=4
    revised,q3=validate_panel(revised)
    save_snapshot(db,revised,q3)
    assert measure(db)==0
    assert db.execute('SELECT actual FROM analytics.commercial_forecast_outcomes').fetchone()[0]==3



def test_source_adapter_excludes_partial_month_and_cam(db):
    from replica_cygnus.commercial_forecasting.service import read_source
    db.execute('''CREATE VIEW analytics.v_absorcion_ventas_mensual AS
      SELECT * FROM (VALUES
        (DATE '2026-09-01','GY',2::bigint,10::bigint,8::bigint,0::bigint,0::bigint,false),
        (DATE '2026-10-01','GY',1::bigint,8::bigint,7::bigint,0::bigint,0::bigint,true),
        (DATE '2026-09-01','CAM',1::bigint,3::bigint,2::bigint,0::bigint,0::bigint,false)
      ) AS v(periodo_mes,codigo_proyecto,ventas_mes,stock_inicial,stock_final,
             ingresos_mes,unidades_revision,mes_parcial)''')
    panel=read_source(db)
    assert len(panel)==1 and panel.project.iloc[0]=='GY'
    clean,q=validate_panel(panel)
    assert clean.month.iloc[0]==pd.Timestamp('2026-09-01')


def insert_pending(db, tmp_path, *, created_at=None):
    panel,q=validate_panel(pd.DataFrame([dict(month='2020-09-01',project='DEMO',sales=2,
        stock_open=10,stock_close=8,inflows=0,review_units=0)]))
    sid=save_snapshot(db,panel,q); rid=str(uuid4())
    manifest=dict(run_id=rid,snapshot_id=sid,selected_model='mean3',evidence_level='HISTORICAL_DIAGNOSTIC_SHADOW',
                  coverage_projects=[dict(project='DEMO',status='FORECAST_AVAILABLE',stock=8,has_forecast=True)])
    if created_at:
        from psycopg.types.json import Jsonb
        db.execute('''INSERT INTO model_control.commercial_forecast_runs
            (run_id,snapshot_id,created_at,manifest,selected_model,evidence_level,artifact_path)
            VALUES (%s,%s,%s,%s,'mean3','HISTORICAL_DIAGNOSTIC_SHADOW',%s)''',
            (rid,sid,created_at,Jsonb(manifest),str(tmp_path)))
        db.execute('''INSERT INTO analytics.commercial_forecast_predictions
            (run_id,project,origin,horizon,model,prediction,stock,is_selected)
            VALUES (%s,'DEMO','2020-09-01',1,'mean3',2,8,true)''',(rid,))
    else:
        forecast=pd.DataFrame([dict(project='DEMO',origin=pd.Timestamp('2020-09-01'),horizon=1,model='mean3',
            prediction=2.,stock=8.,lower80=1.,upper80=3.,lower95=0.,upper95=4.,is_selected=True,state_probabilities=None)])
        store_run(db,tmp_path,manifest,forecast,pd.DataFrame())
    return rid,sid,panel


def test_measure_skips_incomplete_project_snapshot_but_freezes_revised_stock_reason(db,tmp_path):
    rid,sid,panel=insert_pending(db,tmp_path)
    missing=pd.DataFrame([dict(month='2020-10-01',project='OTHER',sales=1,stock_open=5,stock_close=4,inflows=0,review_units=0)])
    missing,q=validate_panel(missing); save_snapshot(db,missing,q)
    assert measure(db)==0
    revised=panel.copy(); revised.loc[0,'sales']=1; revised.loc[0,'stock_close']=9
    october=pd.DataFrame([dict(month='2020-10-01',project='DEMO',sales=3,stock_open=9,stock_close=6,inflows=0,review_units=0)])
    revised,q=validate_panel(pd.concat([revised,october],ignore_index=True))
    sid2=save_snapshot(db,revised,q)
    assert measure(db)==1
    actual,eligible,reason,observed=db.execute('''SELECT actual,eligible_scope,eligibility_reason,outcome_snapshot_id
        FROM analytics.commercial_forecast_outcomes WHERE run_id=%s''',(rid,)).fetchone()
    assert actual==3 and not eligible and reason=='ISSUANCE_STOCK_REVISED' and str(observed)==sid2
    assert measure(db)==0
    assert db.execute('SELECT count(*) FROM analytics.v_commercial_forecast_coverage').fetchone()[0]==1


def test_prospective_flags_use_lima_timestamp_and_legacy_outcomes_are_not_certified(db,tmp_path):
    before,sid,_=insert_pending(db,tmp_path,created_at=datetime(2020,10,1,4,59,59,tzinfo=timezone.utc))
    after,_,_=insert_pending(db,tmp_path,created_at=datetime(2020,10,1,5,0,1,tzinfo=timezone.utc))
    for rid in [before,after]:
        db.execute('''INSERT INTO analytics.commercial_forecast_outcomes
          (run_id,project,horizon,model,outcome_snapshot_id,actual,eligible_scope,eligibility_reason)
          VALUES (%s,'DEMO',1,'mean3',%s,3,true,'COMPATIBLE_SCOPE')''',(rid,sid))
    flags=db.execute('''SELECT run_id,issued_before_window_start,eligible_for_operational_scoring,eligible_for_strict_prospective_scoring
                       FROM analytics.v_commercial_forecast_performance''').fetchall()
    flags={str(r[0]):r[1:] for r in flags}
    assert flags[before]==(True,True,True) and flags[after]==(False,True,False)
    assert db.execute('''SELECT strictly_prospective_outcomes,strictly_prospective_mae,as_issued_wape
      FROM analytics.v_commercial_forecast_monitoring WHERE run_id=%s''',(before,)).fetchone()[0:2]==(1,1)
    legacy,_,_=insert_pending(db,tmp_path,created_at=datetime(2020,9,30,tzinfo=timezone.utc))
    db.execute('''INSERT INTO analytics.commercial_forecast_outcomes
        (run_id,project,horizon,model,outcome_snapshot_id,actual,eligible_scope)
        VALUES (%s,'DEMO',1,'mean3',%s,3,true)''',(legacy,sid))
    assert db.execute('''SELECT eligibility_reason,eligible_for_operational_scoring
        FROM analytics.v_commercial_forecast_performance WHERE run_id=%s''',(legacy,)).fetchone()==('LEGACY_UNASSESSED',False)


def _powerbi_query(name):
    """Run the exact SQL pasted by the Power Query templates, not a duplicate."""
    source=(ROOT/'powerbi/M'/f'{name}.m').read_text(encoding='utf-8')
    block=source.split('[Query = Text.Combine({',1)[1].split('}, " ")]',1)[0]
    return ' '.join(json.loads(line.strip().rstrip(',')) for line in block.splitlines() if line.strip())


def test_forecasting_powerbi_queries_on_disposable_postgres(db,tmp_path):
    rid,_,_=insert_pending(db,tmp_path)
    coverage=db.execute(_powerbi_query('qForecastCoverage')).fetchall()
    assert len(coverage)==1 and coverage[0][0]==rid and coverage[0][1]=='DEMO'
    current=db.execute(_powerbi_query('qForecastCurrent')).fetchall()
    assert len(current)==1 and current[0][0]==rid and current[0][4]=='mean3'
    candidates=db.execute(_powerbi_query('qForecastCandidateStatus')).fetchall()
    assert len(candidates)==1 and candidates[0][1:4]==('mean3',1,1)
    issued=db.execute(_powerbi_query('qForecastAsIssued')).fetchall()
    assert len(issued)==1 and issued[0][9] is None  # No mature outcome yet.
    monthly=db.execute(_powerbi_query('qForecastMonthly')).fetchall()
    assert len(monthly)==1 and monthly[0][1]=='DEMO'
    assert str(monthly[0][5]) == '2020-10-01' and monthly[0][6] == 2 and monthly[0][7] == 2

    db.execute('''CREATE VIEW analytics.v_absorcion_ventas_revision AS
      SELECT 'NP'::text AS codigo_proyecto,'Nápoles'::text AS nombre_proyecto,
      'N-101'::text AS codigo_unidad,'101'::text AS nombre_unidad,
      'Vendido'::text AS estado_comercial_actual,NULL::date AS fecha_venta,
      0::bigint AS ventas_elegibles,1::bigint AS ciclos_revision,
      now() AS ultima_actualizacion_ciclos''')
    db.execute('''CREATE VIEW analytics.v_absorcion_ventas_ciclos AS
      SELECT 'NP'::text AS codigo_proyecto, v.codigo_unidad, v.codigo_proforma,
             v.calidad_ciclo, 'NO_CONFIRMADA'::text AS metodo_fecha_venta,
             NULL::date AS fecha_de_minuta, NULL::date AS fecha_firma_legacy,
             NULL::date AS fecha_venta_documental, NULL::date AS fecha_anulacion,
             'DOCUMENTAL_VS_INVENTARIO'::text AS reconciliation_status,
             'Revisar'::text AS observacion
      FROM (VALUES ('N-101','P-1','FECHA_PAGO_CI_INVALIDA'),
                   ('N-101','P-2','LEGACY_2026_PROHIBIDO'))
           AS v(codigo_unidad,codigo_proforma,calidad_ciclo)''')
    review=db.execute(_powerbi_query('qForecastReviewQueue')).fetchall()
    assert len(review)==1 and review[0][0]=='NP' and review[0][-1]=='CICLO_PENDIENTE'
    assert 'P-1' in review[0][-2] and 'P-2' in review[0][-2]
    cases=read_review_cases(db,['NP','SL','TZ'])
    assert cases['distinct_review_units']==1 and len(cases['cycles'])==2
    assert cases['units'][0]['codigo_unidad']=='N-101'
    assert cases['units'][0]['ciclo_pendiente'] is True
