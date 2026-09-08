from datetime import date

from test_lead_pilot_postgres import db, ROOT
from replica_cygnus.lead_scoring.history_diagnostic import parameters, summarize


def test_historical_sql_dedup_before_window_and_no_write(db):
    # Client A existed before the window: reassignment must not count as new.
    entries=[('a0','A','P1','2025-12-01T12:00:00-05:00',0,0,'2026-03-01'),
             ('a1','A','P1','2026-01-01T12:00:00-05:00',1,0,'2026-03-01'),
             ('b0','B','P1','2026-01-01T12:00:00-05:00',1,0,'2026-03-01'),
             ('b1','B','P2','2026-01-02T12:00:00-05:00',0,0,'2026-03-01'),
             ('c0','C','P1','2026-01-02T12:00:00-05:00',None,None,None),
             ('bad','','P1','2026-01-02T12:00:00-05:00',None,None,None),
             ('late','L','P1','2026-03-01T00:00:00-05:00',None,None,None)]
    for key,document,project,when,sep,minuta,asof in entries:
        db.execute('''INSERT INTO features.lead_evidence(evidence_key,lead_id,decision_at,evidence_source,
          documento_cliente,codigo_proyecto,separacion_14d,minuta_60d,labels_as_of)
          VALUES (%s,%s,%s,'BACKFILL_INFERRED',%s,%s,%s,%s,%s)''',(key,key,when,document,project,sep,minuta,asof))
    before=db.execute('SELECT count(*) FROM features.lead_evidence').fetchone()[0]
    data=db.execute((ROOT/'sql/lead_pilot_history_readonly.sql').read_text(),parameters(date(2026,1,1),date(2026,3,1))).fetchone()[0]
    result=summarize(data,date(2026,1,1),date(2026,3,1))
    p1=next(p for p in result['projects'] if p['project']=='P1')
    p2=next(p for p in result['projects'] if p['project']=='P2')
    assert p1['assignments']==3 and p1['first_client_project']==2
    assert p1['sep_mature']==2 and p1['sep_positive']==1 and p1['sep_missing']==1
    assert p1['minuta_mature']==0  # 59 days: neither first client has completed 60 days
    assert p2['first_client_project']==1 and p2['first_client_global']==0
    assert result['quality']['window_source_rows']==5 and result['quality']['invalid_identity_or_project']==1
    assert result['excluded_at_or_after_cutoff']==1
    assert db.execute('SELECT count(*) FROM features.lead_evidence').fetchone()[0]==before
