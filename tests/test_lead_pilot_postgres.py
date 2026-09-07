"""Integration gate. Dedicated empty DB only; all fixture writes roll back.

Set PILOT_TEST_DSN explicitly. Never use application settings/production credentials.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from replica_cygnus.lead_scoring.pilot import create_pilot, set_status, enroll, import_events
from test_lead_pilot import protocol

ROOT=Path(__file__).resolve().parents[1]
UTC=timezone.utc


@pytest.fixture
def db():
    dsn=os.environ.get("PILOT_TEST_DSN")
    if not dsn:
        pytest.skip("PILOT_TEST_DSN no configurado: requiere base aislada vacía")
    with psycopg.connect(dsn,autocommit=True) as conn:
        assert conn.execute("SELECT to_regnamespace('experiments')").fetchone()[0] is None, "Solo base de pruebas vacía"
        with conn.transaction(force_rollback=True):
            for filename in ["init_decision_intelligence.sql","init_lead_scoring.sql","init_lead_pilot.sql","init_lead_pilot.sql"]:
                conn.execute((ROOT/'sql'/filename).read_text())
            yield conn


def test_pilot_real_sql_end_to_end(db):
    p=protocol()
    model=p['model_run_id']
    db.execute("""INSERT INTO model_control.model_runs(model_run_id,decision_system,model_name,model_version)
                  VALUES (%s,'priorizacion_leads','lead_priority_bundle','synthetic-test')""",(model,))
    db.execute("INSERT INTO model_control.model_aliases(decision_system,model_name,alias_name,model_run_id) VALUES ('priorizacion_leads','lead_priority_bundle','serving',%s)",(model,))
    assert create_pilot(db,p,"test")=="CREATED_DRAFT"
    assert create_pilot(db,p,"test")=="EXISTING"
    with pytest.raises(ValueError,match="inmutable"):
        create_pilot(db,{**p,"sla_minutes":30},"test")
    with pytest.raises(ValueError,match="ACTIVE"):
        enroll(db,p['pilot_id'],"test",{},True)
    set_status(db,p['pilot_id'],"ACTIVE","test")
    # Fixture deliberately places start in past, to allow new leads with stale/before-start cases.
    start=datetime.now(UTC)-timedelta(hours=2)
    db.execute("UPDATE experiments.lead_pilots SET activated_at=%s WHERE pilot_id=%s",(start,p['pilot_id']))
    for key,doc,source,delta in [('a','0001','LIVE',1),('a2','0001','LIVE',1),('b','0002','LIVE',1),
                                 ('backfill','0003','BACKFILL_INFERRED',1),('old','0004','LIVE',-2)]:
        when=start+timedelta(hours=delta)
        db.execute("""INSERT INTO features.lead_evidence(evidence_key,lead_id,decision_at,evidence_source,documento_cliente,codigo_proyecto)
                      VALUES (%s,%s,%s,%s,%s,'P1')""",(key,key,when,source,doc))
        db.execute("""INSERT INTO decision_intelligence.lead_scores
        (score_id,evidence_key,lead_id,decision_at,scored_at,model_run_id,p_separacion_14d,p_minuta_60d,priority_score,priority_rank,priority_band)
        VALUES (%s,%s,%s,%s,%s,%s,.1,.05,10,1,'A')""",(uuid4(),key,key,when,when,model))
    roster={key:'review/test' for key in ['a','a2','b','backfill','old','missing']}
    preview=enroll(db,p['pilot_id'],"test",roster)
    assert preview['accepted_rows']==2 and preview['existing_rows']==1 and preview['rejected_rows']==3
    assert db.execute("SELECT count(*) FROM experiments.lead_pilot_assignments").fetchone()[0]==0
    result=enroll(db,p['pilot_id'],"test",roster,True)
    assert result['reconciled'] and result['accepted_rows']==2
    assert {r[2] for r in result['rejects']}=={'NOT_LIVE','NOT_PROSPECTIVE_OR_INVALID_TIME','NO_SCORE_FOR_FROZEN_MODEL'}
    retry=enroll(db,p['pilot_id'],"test",roster,True)
    assert retry['accepted_rows']==0 and retry['existing_rows']==3
    assert db.execute("SELECT count(*) FROM experiments.lead_pilot_assignments").fetchone()[0]==2
    assert db.execute("SELECT count(*) FROM experiments.v_lead_pilot_operations").fetchone()[0]==2
    assert db.execute("SELECT count(*) FROM experiments.v_lead_pilot_monitor").fetchone()[0]==4
    aid=result['assignments'][0]['assignment_id']
    # Test-only time travel, never offered by CLI. Makes both outcome horizons mature.
    assigned=datetime.now(UTC)-timedelta(days=61)
    db.execute("UPDATE experiments.lead_pilot_assignments SET assigned_at=%s WHERE assignment_id=%s",(assigned,aid))
    base=dict(assignment_id=aid,action_at=(assigned+timedelta(minutes=5)).isoformat(),
              action_type='CALL',result='NO_ANSWER',owner='test',cost_pen='1.2500',source_ref='crm/test')
    actions=[dict(base,event_id=str(uuid4())),dict(base,event_id=str(uuid4()),action_type='WHATSAPP'),
             dict(base,event_id=str(uuid4()),cost_pen='-1')]
    a=import_events(db,p['pilot_id'],actions,'actions','test')
    assert (a['source_rows'],a['accepted_rows'],a['existing_rows'],a['rejected_rows'])==(3,2,0,1)
    again=import_events(db,p['pilot_id'],actions[:2],'actions','test')
    assert again['existing_rows']==2 and again['accepted_rows']==0
    conflict=import_events(db,p['pilot_id'],[{**actions[0],'result':'CHANGED'}],'actions','test')
    assert conflict['rejected_rows']==1
    rows=[dict(assignment_id=aid,outcome_name='separacion_14d',value='1',event_at=(assigned+timedelta(days=2)).isoformat(),
               observed_through=datetime.now(UTC).isoformat(),verified_by='test',source_ref='process/test'),
          dict(assignment_id=aid,outcome_name='minuta_60d',value='0',event_at='',
               observed_through=datetime.now(UTC).isoformat(),verified_by='test',source_ref='process/test')]
    o=import_events(db,p['pilot_id'],rows,'outcomes','test')
    assert o['accepted_rows']==2
    assert import_events(db,p['pilot_id'],rows,'outcomes','test')['existing_rows']==2
    count,total=db.execute("SELECT count(*),sum(cost_pen) FROM experiments.v_lead_pilot_operations").fetchone()
    assert count==2 and float(total)==2.5  # two actions are not multiplied by two outcomes
    assert db.execute("SELECT sum(outcome_value) FROM experiments.v_lead_pilot_monitor WHERE outcome_name='separacion_14d'").fetchone()[0]==1
    assert db.execute("SELECT bool_and(reconciled) FROM experiments.v_lead_pilot_reconciliation").fetchone()[0]
    assert db.execute("SELECT sum(accepted_rows) FROM experiments.lead_pilot_batches WHERE batch_type='ACTIONS'").fetchone()[0]==db.execute("SELECT count(*) FROM experiments.lead_pilot_actions").fetchone()[0]
    set_status(db,p['pilot_id'],'PAUSED','test')
    with pytest.raises(ValueError,match='ACTIVE'): enroll(db,p['pilot_id'],'test',roster,True)
    set_status(db,p['pilot_id'],'CLOSED','test')
    with pytest.raises(ValueError,match='Transición'): set_status(db,p['pilot_id'],'ACTIVE','test')
