"""Import an aggregate ML impact planning workbook into local Medallio PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from replica_cygnus.ml_impact import parse_workbook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga un corte comercial agregado para escenarios de impacto")
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--as-of", required=True, type=date.fromisoformat,
                        help="Fecha real de corte comercial, AAAA-MM-DD (no inferida de la creación del Excel)")
    parser.add_argument("--source-note", default=None, help="Procedencia y definición acordada del corte")
    parser.add_argument("--check-only", action="store_true", help="Valida el archivo sin conectar al DW")
    args = parser.parse_args(argv)

    path = args.workbook.resolve(strict=True)
    metrics, diagnostics = parse_workbook(path)
    digest = sha256(path.read_bytes()).hexdigest()
    print(f"Archivo={path.name} | corte={args.as_of} | sha256={digest} | "
          f"proyectos={len(diagnostics)} | indicadores={len(metrics)}")
    for item in diagnostics:
        print(f"{item['code']:>4} {item['project']}: gap reportado - matemático = "
              f"S/ {item['gap_difference']:,.2f}; diferencia stock = S/ {item['stock_difference']:,.2f}")
    if args.check_only:
        return 0

    from replica_cygnus.connections import connect_postgres
    from replica_cygnus.settings import load_settings

    settings = load_settings(Path(__file__).resolve().parents[1], require_source=False)
    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('decision_intelligence.ml_impact_snapshot')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("Instalar antes: python scripts/schema_sync.py --only ml_impact")
            codes = [d["code"] for d in diagnostics]
            cur.execute("SELECT codigo_proyecto FROM core.dim_proyecto WHERE codigo_proyecto = ANY(%s)", (codes,))
            found = {row[0] for row in cur.fetchall()}
            if found != set(codes):
                raise ValueError(f"Faltan códigos en core.dim_proyecto: {sorted(set(codes)-found)}")
            snapshot_id = uuid4()
            cur.execute(
                """INSERT INTO decision_intelligence.ml_impact_snapshot
                   (snapshot_id,as_of_date,source_name,source_sha256,source_note)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (as_of_date,source_sha256) DO NOTHING
                   RETURNING snapshot_id""",
                (snapshot_id, args.as_of, path.name, digest, args.source_note),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute("""SELECT snapshot_id FROM decision_intelligence.ml_impact_snapshot
                               WHERE as_of_date=%s AND source_sha256=%s""", (args.as_of, digest))
                print(f"Corte idéntico ya importado: {cur.fetchone()[0]}")
                return 0
            cur.executemany(
                """INSERT INTO decision_intelligence.ml_impact_metric
                   (snapshot_id,codigo_proyecto,nombre_proyecto_fuente,bloque,indicador,tipo,
                    valor_original,valor,cantidad)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(snapshot_id, m.code, m.project, m.block, m.indicator, m.metric_type,
                  m.original, m.value, m.quantity) for m in metrics],
            )
        print(f"Corte importado: {snapshot_id}. Consultar decision_intelligence.v_ml_impact_portafolio_actual")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
