from datetime import date
from decimal import Decimal
import pytest
from replica_cygnus.publishing.factory import demo_snapshot
from replica_cygnus.publishing.local import capture_snapshot

class Cursor:
    def __init__(self,rows):self.rows=rows;self.calls=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,*args):self.calls.append(args)
    def fetchall(self):return self.rows

class Connection:
    def __init__(self,rows):self.cur=Cursor(rows)
    def cursor(self):return self.cur


def test_capture_existing_contract_only():
    rows=[(r['project'],date.fromisoformat(r['period']),Decimal(r['stock_open']),r['sales'],r['stock_close'],0) for r in demo_snapshot()['rows']]
    conn=Connection(rows)
    result=capture_snapshot(conn,'2026-10-09')
    assert result['semantics']=='RECONSTRUCTED_REVISED_HISTORY'
    assert result['rows'][0]['period']=='2026-01-01'
    assert 'READ ONLY' in conn.cur.calls[0][0]
    query,params=conn.cur.calls[-1]
    assert 'analytics.comercial_proyecto_mes' in query
    assert 'LIMIT 10001' in query
    assert params==('2026-10-09',)
    assert 'raw_' not in query
