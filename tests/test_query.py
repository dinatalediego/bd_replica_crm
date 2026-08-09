from replica_cygnus.models import SourceColumn, SyncState, TableConfig
from replica_cygnus.query_builder import build_source_query


def columns():
    return [
        SourceColumn("id", "bigint", 1, False),
        SourceColumn("fecha_actualizacion", "timestamp without time zone", 2, True),
        SourceColumn("nombre", "character varying", 3, True, 100),
    ]


def test_initial_incremental_query_has_no_select_star():
    cfg = TableConfig(
        source_schema="grupocygnus",
        source_table="clientes",
        key_columns=["id"],
        watermark_column="fecha_actualizacion",
        enabled=True,
    )
    query, params = build_source_query(cfg, columns(), SyncState(None, None), max_rows=500)
    assert "SELECT *" not in query
    assert '"id"' in query
    assert "LIMIT 500" in query
    assert params == ()


def test_incremental_query_uses_watermark():
    cfg = TableConfig(
        source_schema="grupocygnus",
        source_table="clientes",
        key_columns=["id"],
        watermark_column="fecha_actualizacion",
        lookback_hours=48,
        enabled=True,
    )
    query, params = build_source_query(
        cfg,
        columns(),
        SyncState("2026-08-06T12:00:00", "timestamp without time zone"),
    )
    assert '"fecha_actualizacion" >= %s' in query
    assert params[0].isoformat() == "2026-08-04T12:00:00"
