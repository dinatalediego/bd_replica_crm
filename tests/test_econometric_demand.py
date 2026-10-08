"""Exercise configured aggregation and missing-source handling without customer data."""
from datetime import date
import json
from replica_cygnus.econometric_datasets.service import collect_demand


class Cursor:
    def __init__(self,conn): self.conn=conn;self.results=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,query,params=None):
        text=str(query)
        self.conn.queries.append(text)
        if 'information_schema.columns' in text:
            self.results=[(x,) for x in ('project','created','id','client')] if params[1]=='leads' else []
        elif 'count(DISTINCT' in text:
            self.results=[('P',date(2024,1,8),3,2,0)]
        elif 'WITH bounds' in text:
            self.results=[('P',date(2024,1,1),0,0,0),('P',date(2024,1,8),1,0,0),('P',date(2024,1,15),0,1,0)]
        else: self.results=[]
    def fetchall(self): return self.results
    def executemany(self,query,rows):
        if 'panel_demanda' in str(query): self.conn.rows=list(rows)


class Conn:
    def __init__(self): self.queries=[];self.rows=[]
    def cursor(self): return Cursor(self)


def test_missing_source_null_history_before_coverage_null_and_later_zero(tmp_path):
    spec={'enabled':True,'schema':'raw','table':'leads','project':'project','date':'created','id':'id','client':'client'}
    cfg=tmp_path/'sources.json';cfg.write_text(json.dumps({'asignaciones':spec,'proformas':dict(spec,table='missing')}))
    conn=Conn();status=collect_demand(conn,cfg)
    assert status['asignaciones']=='OK'
    assert status['proformas'].startswith('MISSING_COLUMNS')
    # assignment count and unique clients; not a client PII export.
    assert conn.rows[0][2:4]==(None,None)
    assert conn.rows[1][2:4]==(3,2)
    assert conn.rows[2][2:4]==(0,0)
    assert all(row[4] is None for row in conn.rows) # missing proformas, not zero
    assert all(row[6] is None for row in conn.rows) # visits contract absent
