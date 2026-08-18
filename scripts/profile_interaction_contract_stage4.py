from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def _fetch(conn, query: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query)
        return [dict(r) for r in cur.fetchall()]


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else fallback
    with path.open('w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    settings = load_settings()
    out = settings.project_root / 'reports' / 'interaction_contract_stage4'
    out.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        identity = _fetch(conn, r"""
        with base as (
            select id, tipo::text as tipo, fecha_creacion,
                   nullif(btrim(documento_cliente::text), '') as documento_cliente,
                   nullif(btrim(cliente_id::text), '') as cliente_id
            from raw_cygnus.interacciones
        ), candidates as (
            select 'id'::text as candidate_key, count(*)::bigint as duplicate_groups
            from (select id from base group by id having count(*) > 1) x
            union all
            select 'tipo,id', count(*)::bigint
            from (select tipo,id from base group by tipo,id having count(*) > 1) x
            union all
            select 'id,fecha_creacion', count(*)::bigint
            from (select id,fecha_creacion from base group by id,fecha_creacion having count(*) > 1) x
            union all
            select 'tipo,id,fecha_creacion', count(*)::bigint
            from (select tipo,id,fecha_creacion from base group by tipo,id,fecha_creacion having count(*) > 1) x
            union all
            select 'tipo,id,cliente_id,fecha_creacion', count(*)::bigint
            from (select tipo,id,cliente_id,fecha_creacion from base group by tipo,id,cliente_id,fecha_creacion having count(*) > 1) x
        )
        select candidate_key, duplicate_groups,
               (duplicate_groups = 0) as unique_candidate
        from candidates
        order by duplicate_groups, candidate_key
        """)

        update_clock = _fetch(conn, r"""
        with b as (
            select
                fecha_creacion::timestamp as created_at,
                fecha_actualizacion,
                hora_actualizacion::text as hora_actualizacion,
                case
                    when hora_actualizacion::text ~ '^([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9](\.[0-9]+)?)?$'
                    then fecha_actualizacion::timestamp + hora_actualizacion::time
                    else null::timestamp
                end as updated_at
            from raw_cygnus.interacciones
        ), d as (
            select *, extract(epoch from (updated_at-created_at))/3600.0 as delta_hours
            from b
        )
        select
            count(*)::bigint as rows,
            count(*) filter (where nullif(btrim(hora_actualizacion),'') is not null)::bigint as nonblank_update_time_rows,
            count(updated_at)::bigint as parseable_update_timestamp_rows,
            count(*) filter (where updated_at is not null and created_at <= updated_at)::bigint as creation_at_or_before_update_rows,
            count(*) filter (where updated_at is not null and created_at > updated_at)::bigint as creation_after_update_rows,
            percentile_cont(0.5) within group (order by delta_hours) filter (where updated_at is not null) as median_update_minus_creation_hours,
            percentile_cont(0.9) within group (order by delta_hours) filter (where updated_at is not null) as p90_update_minus_creation_hours
        from d
        """)

        direct_family = _fetch(conn, r"""
        select
            tipo::text as tipo,
            tipo_interaccion::text as tipo_interaccion,
            estado::text as estado,
            count(*)::bigint as rows,
            count(*) filter (
                where codigo_proforma::text in (
                    select distinct codigo_proforma::text
                    from core.fact_ciclo_comercial_unidad
                    where codigo_proforma is not null
                )
            )::bigint as rows_matching_core
        from raw_cygnus.interacciones
        where nullif(btrim(codigo_proforma::text), '') is not null
        group by tipo, tipo_interaccion, estado
        order by count(*) desc
        """)

        behavior_family = _fetch(conn, r"""
        with training_clients as (
            select
                nullif(btrim(documento_cliente::text), '') as documento_cliente,
                count(distinct separation_id)::bigint as lifecycle_count
            from decision_intelligence.v_separation_fall_training_outcome
            where nullif(btrim(documento_cliente::text), '') is not null
            group by 1
        )
        select
            i.tipo::text as tipo,
            i.tipo_interaccion::text as tipo_interaccion,
            i.estado::text as estado,
            count(*)::bigint as rows,
            count(*) filter (where tc.documento_cliente is not null)::bigint as rows_for_training_clients,
            count(*) filter (where tc.lifecycle_count = 1)::bigint as rows_for_single_lifecycle_training_clients,
            count(*) filter (where tc.lifecycle_count > 1)::bigint as rows_for_multi_lifecycle_training_clients
        from raw_cygnus.interacciones i
        left join training_clients tc
          on tc.documento_cliente = nullif(btrim(i.documento_cliente::text), '')
        where nullif(btrim(i.codigo_proforma::text), '') is null
        group by i.tipo, i.tipo_interaccion, i.estado
        order by rows_for_training_clients desc, rows desc
        """)

    _write_csv(out/'identity_candidate_health.csv', identity, ['candidate_key','duplicate_groups'])
    _write_csv(out/'update_clock_health.csv', update_clock, ['rows'])
    _write_csv(out/'direct_proforma_event_family.csv', direct_family, ['tipo','tipo_interaccion','estado','rows'])
    _write_csv(out/'training_client_event_family.csv', behavior_family, ['tipo','tipo_interaccion','estado','rows'])

    identity_winners = [r['candidate_key'] for r in identity if r.get('unique_candidate')]
    summary = {
        'status': 'STAGE4_PROFILED_NOT_CERTIFIED',
        'identity_unique_candidates': identity_winners,
        'update_clock_health': update_clock[0] if update_clock else {},
        'event_time_policy_candidate': {
            'ACTIVIDAD': 'fecha_creacion is candidate record/event timestamp; requires stage4 empirical review before certification',
            'EVENTO': 'exclude from behavioral v1 until scheduled-vs-realized semantics are certified',
            'fecha_actualizacion': 'do not use date alone; pair with hora_actualizacion only for audit/update chronology',
            '_etl_loaded_at': 'never behavioral event time',
        },
        'behavioral_v1_candidate_policy': {
            'include_only_estado': 'realizado',
            'exclude_tipo_interaccion': [
                'creación de cliente', 'creación de proforma', 'creación de proforma web',
                'api', 'creacion de evento'
            ],
            'linkage': 'documento_cliente with temporal lifecycle attribution; never fan-out multi-lifecycle clients',
            'as_of_rule': 'interaction_event_at <= snapshot_at',
        },
        'next_gate': 'If a composite identity is unique and fecha_creacion behaves consistently for ACTIVIDAD, create canonical analytics.interaction_event_v1 and point-in-time behavioral features; keep EVENTO and post-outcome fields excluded.',
        'outputs': [
            'identity_candidate_health.csv', 'update_clock_health.csv',
            'direct_proforma_event_family.csv', 'training_client_event_family.csv'
        ],
    }
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
