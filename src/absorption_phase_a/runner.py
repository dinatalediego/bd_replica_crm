from __future__ import annotations
import argparse,json,os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
ROOT=Path(__file__).resolve().parents[2]
SQL_DIR=ROOT/'sql'/'10_absorption_phase_a'
METADATA=['00_preflight_control_and_schemas.sql','01_inventory_metadata.sql','02_find_datos_extras.sql']
TARGETED=['03_process_event_domain.sql','04_business_key_cardinality.sql','05_proforma_unidad_relationships.sql','06_sale_date_dependency_probe.sql','07_stock_entry_candidate_probe.sql','08_temporal_sequences_probe.sql','09_performance_probe.sql','10_data_quality_probe.sql']
def envload():
 p=ROOT/'.env'
 if p.exists():
  for raw in p.read_text(encoding='utf-8').splitlines():
   s=raw.strip()
   if s and not s.startswith('#') and '=' in s:
    k,v=s.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
def dsn():
 envload(); return f"host={os.getenv('POSTGRES_HOST','localhost')} port={os.getenv('POSTGRES_PORT','5432')} dbname={os.getenv('POSTGRES_DATABASE','medallio_dw')} user={os.getenv('POSTGRES_USER','postgres')} password={os.getenv('POSTGRES_PASSWORD','')} sslmode={os.getenv('POSTGRES_SSLMODE','prefer')}"
def clean_statements(text):
 lines=[ln for ln in text.splitlines() if not ln.lstrip().startswith('--')]
 return [s.strip() for s in '\n'.join(lines).split(';') if s.strip()]
def main():
 ap=argparse.ArgumentParser(); g=ap.add_mutually_exclusive_group(required=True); g.add_argument('--metadata-only',action='store_true'); g.add_argument('--all',action='store_true'); args=ap.parse_args()
 scripts=METADATA if args.metadata_only else METADATA+TARGETED
 with psycopg.connect(dsn()) as conn:
  db=conn.execute('select current_database()').fetchone()[0]
  if db!=os.getenv('POSTGRES_DATABASE','medallio_dw'): raise RuntimeError(f'Base inesperada: {db}')
  exists=conn.execute("SELECT to_regclass('observability.absorption_discovery_runs') IS NOT NULL AND to_regclass('observability.absorption_discovery_results') IS NOT NULL").fetchone()[0]
  if not exists:
   raise RuntimeError('No existe registry de discovery. Ejecuta primero 00_preflight_control_and_schemas.sql y, solo si no hay estructura equivalente, 11_optional_discovery_registry.sql')
  run_id=conn.execute("INSERT INTO observability.absorption_discovery_runs(notes) VALUES (%s) RETURNING discovery_run_id",(f'Phase A scripts={len(scripts)}',)).fetchone()[0]; conn.commit()
  try:
   for fn in scripts:
    print('[RUN]',fn)
    for i,stmt in enumerate(clean_statements((SQL_DIR/fn).read_text(encoding='utf-8')),1):
     with conn.cursor(row_factory=dict_row) as cur:
      cur.execute(stmt)
      if cur.description:
       for n,row in enumerate(cur.fetchall(),1):
        conn.execute("INSERT INTO observability.absorption_discovery_results(discovery_run_id,query_name,row_number_in_result,payload) VALUES (%s,%s,%s,%s::jsonb)",(run_id,f'{fn}::statement_{i}',n,json.dumps(row,default=str,ensure_ascii=False)))
     conn.commit()
   conn.execute("UPDATE observability.absorption_discovery_runs SET finished_at=now(),status='SUCCESS' WHERE discovery_run_id=%s",(run_id,)); conn.commit(); print('SUCCESS run',run_id)
  except Exception:
   conn.execute("UPDATE observability.absorption_discovery_runs SET finished_at=now(),status='FAILED' WHERE discovery_run_id=%s",(run_id,)); conn.commit(); raise
if __name__=='__main__': main()
