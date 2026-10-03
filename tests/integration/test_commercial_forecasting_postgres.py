"""Disposable PostgreSQL only; mirrors the existing absorption integration fixture."""
from datetime import date, datetime, timezone
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import pandas as pd
import pytest

from replica_cygnus.commercial_forecasting.service import (
    ensure_schema, measure, save_snapshot, store_run,
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
