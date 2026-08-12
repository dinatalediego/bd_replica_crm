from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .catalog import discover_source
from .config import load_table_configs
from .connections import connect_postgres, connect_redshift
from .errors import ReplicaError
from .decision_schema import ensure_decision_intelligence
from .decision_intelligence.config import load_decision_contracts
from .decision_intelligence.demo import run_demo
from .logging_config import configure_logging
from .metadata import ensure_control_tables, recent_runs
from .settings import load_settings
from .sync import select_configs, sync_table
from .validation import validate_source_config
from .observability.schema import ensure_observability
from .observability.service import register_all_assets, run_observability

LOGGER = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replica-cygnus",
        description="Réplica incremental Amazon Redshift -> PostgreSQL local",
    )
    parser.add_argument(
        "--config",
        default="config/tables.yml",
        help="Ruta al YAML de tablas, relativa a la raíz del proyecto.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Crea réplica + capa de Decision Intelligence en PostgreSQL local.")
    sub.add_parser("decision-demo", help="Genera un CSV sintético de decisiones priorizadas por valor esperado.")
    contracts = sub.add_parser("decision-contracts", help="Valida y muestra contratos de decisión.")
    contracts.add_argument(
        "--decision-config",
        default="config/decision_systems.yml",
        help="Ruta al YAML de contratos de decisión.",
    )
    sub.add_parser("test-connections", help="Prueba las conexiones de origen y destino.")

    discover = sub.add_parser("discover", help="Genera catálogo CSV y YAML sugerido desde Redshift.")
    discover.add_argument("--schema", default="grupocygnus", help="Esquema de Redshift a descubrir.")

    validate = sub.add_parser("validate", help="Valida llaves, watermark y columnas configuradas.")
    validate.add_argument("--only", help="Tabla específica: tabla o esquema.tabla.")
    validate.add_argument("--include-disabled", action="store_true")
    validate.add_argument("--deep", action="store_true", help="Busca también llaves duplicadas; puede tardar.")

    sync = sub.add_parser("sync", help="Ejecuta la sincronización de tablas habilitadas.")
    sync.add_argument("--only", help="Tabla específica: tabla o esquema.tabla.")
    sync.add_argument("--include-disabled", action="store_true")
    sync.add_argument("--max-rows", type=int, help="Límite de seguridad para una prueba.")
    sync.add_argument("--dry-run", action="store_true", help="Muestra la consulta sin extraer filas.")

    status = sub.add_parser("status", help="Muestra las ejecuciones recientes.")
    status.add_argument("--limit", type=int, default=30)

    obs_init = sub.add_parser("observability-init", help="Crea observabilidad y registra activos configurados.")
    obs_init.add_argument("--observability-config", default="config/observability.yml")

    observe = sub.add_parser("observe", help="Toma snapshots de salud para Power BI Control Tower.")
    observe.add_argument("--mode", choices=["hourly", "deep"], default="hourly")
    observe.add_argument("--only", help="Tabla específica: tabla o esquema.tabla.")
    observe.add_argument("--include-disabled", action="store_true")
    observe.add_argument("--observability-config", default="config/observability.yml")
    return parser


def _resolve_config(root: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def _print_table(headers: list[str], rows: list[tuple]) -> None:
    if not rows:
        print("Sin registros.")
        return
    normalized = [["" if value is None else str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in normalized:
        for i, value in enumerate(row):
            widths[i] = min(max(widths[i], len(value)), 60)

    def crop(value: str, width: int) -> str:
        return value if len(value) <= width else value[: width - 1] + "…"

    print(" | ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in normalized:
        print(" | ".join(crop(value, widths[i]).ljust(widths[i]) for i, value in enumerate(row)))


def command_init(settings) -> int:
    with connect_postgres(settings) as target:
        ensure_control_tables(target)
        with target.cursor() as cursor:
            for schema in ("raw_cygnus", "staging", "analytics"):
                cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        target.commit()
        ensure_decision_intelligence(target, settings.project_root)
        ensure_observability(target, settings.project_root)
    print(
        "PostgreSQL local inicializado: raw_cygnus, staging, analytics, etl_control, "
        "features, decision_intelligence, model_control, experiments y observability."
    )
    return 0


def command_test_connections(settings) -> int:
    source = connect_redshift(settings)
    try:
        with source.cursor() as cursor:
            cursor.execute("SELECT current_database, current_user, current_timestamp")
            source_row = cursor.fetchone()
    finally:
        source.close()

    with connect_postgres(settings) as target:
        with target.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, current_timestamp")
            target_row = cursor.fetchone()

    print(f"Redshift OK   | base={source_row[0]} | usuario={source_row[1]} | hora={source_row[2]}")
    print(f"PostgreSQL OK | base={target_row[0]} | usuario={target_row[1]} | hora={target_row[2]}")
    return 0


def command_discover(settings, schema: str) -> int:
    source = connect_redshift(settings)
    try:
        catalog_path, generated_path = discover_source(
            source,
            settings.project_root / "reports",
            settings.project_root / "config",
            schema_filter=schema,
        )
    finally:
        source.close()
    print(f"Catálogo creado: {catalog_path}")
    print(f"Configuración sugerida: {generated_path}")
    print("Todas las tablas quedan enabled: false. Revisa llaves y watermark antes de activar.")
    return 0


def command_validate(settings, config_path: Path, only: str | None, include_disabled: bool, deep: bool) -> int:
    configs = select_configs(
        load_table_configs(config_path), only=only, include_disabled=include_disabled
    )
    source = connect_redshift(settings)
    has_errors = False
    try:
        for cfg in configs:
            report = validate_source_config(source, cfg, deep=deep)
            print(f"\n[{report.source_name}]")
            for message in report.messages:
                print(f"  {message}")
            has_errors = has_errors or not report.ok
    finally:
        source.close()
    return 1 if has_errors else 0


def command_sync(
    settings,
    config_path: Path,
    only: str | None,
    include_disabled: bool,
    max_rows: int | None,
    dry_run: bool,
) -> int:
    configs = select_configs(
        load_table_configs(config_path), only=only, include_disabled=include_disabled
    )
    if not configs:
        print("No hay tablas habilitadas. Edita config/tables.yml y cambia enabled: true.")
        return 0

    source = connect_redshift(settings)
    target = connect_postgres(settings)
    failures = 0
    try:
        ensure_control_tables(target)
        for cfg in configs:
            try:
                result = sync_table(
                    source,
                    target,
                    cfg,
                    max_rows=max_rows,
                    dry_run=dry_run,
                )
                print(
                    f"{result.status}: {result.source_name} -> {result.target_name} | "
                    f"extraídas={result.rows_extracted} cargadas={result.rows_loaded} | "
                    f"watermark={result.watermark_after}"
                )
                if result.message:
                    print(result.message)
            except Exception as exc:
                failures += 1
                LOGGER.exception("Falló la tabla %s", cfg.source_name)
                print(f"FAILED: {cfg.source_name}: {exc}", file=sys.stderr)
    finally:
        source.close()
        target.close()
    return 1 if failures else 0


def command_status(settings, limit: int) -> int:
    with connect_postgres(settings) as target:
        ensure_control_tables(target)
        rows = recent_runs(target, limit=limit)
    _print_table(
        [
            "inicio",
            "fin",
            "estado",
            "origen",
            "destino",
            "estrategia",
            "extraídas",
            "cargadas",
            "wm antes",
            "wm después",
            "error",
        ],
        rows,
    )
    return 0



def command_decision_demo(settings) -> int:
    output = run_demo(settings.project_root / "reports" / "decision_demo.csv")
    print(f"Demo de Decision Intelligence creada: {output}")
    print("No usa datos reales. Sirve para validar la lógica probabilidad -> valor -> acción.")
    return 0


def command_decision_contracts(settings, config_value: str) -> int:
    config_path = _resolve_config(settings.project_root, config_value)
    contracts = load_decision_contracts(config_path)
    rows = []
    for item in contracts:
        rows.append(
            (
                item.name,
                item.decision_unit,
                item.decision_owner,
                item.target,
                item.prediction_horizon_days,
                item.primary_value_metric,
            )
        )
    _print_table(
        ["sistema", "unidad", "owner", "target", "horizonte_días", "métrica_valor"],
        rows,
    )
    print(f"Contratos válidos: {len(contracts)}")
    return 0


def command_observability_init(settings, config_path: Path, observability_config: str) -> int:
    obs_path = _resolve_config(settings.project_root, observability_config)
    count = register_all_assets(settings, config_path, obs_path)
    print(f"Observabilidad inicializada. Activos registrados: {count}")
    return 0


def command_observe(
    settings,
    config_path: Path,
    observability_config: str,
    mode: str,
    only: str | None,
    include_disabled: bool,
) -> int:
    obs_path = _resolve_config(settings.project_root, observability_config)
    rows = run_observability(
        settings, config_path, obs_path, mode=mode, only=only, include_disabled=include_disabled
    )
    if not rows:
        print("No hay activos seleccionados para monitorear.")
        return 0
    _print_table(
        ["activo", "modo", "salud", "score", "quality", "lag_min", "desde_exito_min"],
        [
            (
                r["asset_key"], r["mode"], r["health_status"],
                r["operational_health_score"], r["quality_score"],
                r["replication_lag_minutes"], r["minutes_since_success"]
            )
            for r in rows
        ],
    )
    return 0

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings()
        configure_logging(settings.project_root / "logs", settings.log_level)
        config_path = _resolve_config(settings.project_root, args.config)

        if args.command == "init":
            return command_init(settings)
        if args.command == "test-connections":
            return command_test_connections(settings)
        if args.command == "decision-demo":
            return command_decision_demo(settings)
        if args.command == "decision-contracts":
            return command_decision_contracts(settings, args.decision_config)
        if args.command == "discover":
            return command_discover(settings, args.schema)
        if args.command == "validate":
            return command_validate(
                settings, config_path, args.only, args.include_disabled, args.deep
            )
        if args.command == "sync":
            return command_sync(
                settings,
                config_path,
                args.only,
                args.include_disabled,
                args.max_rows,
                args.dry_run,
            )
        if args.command == "status":
            return command_status(settings, args.limit)
        if args.command == "observability-init":
            return command_observability_init(settings, config_path, args.observability_config)
        if args.command == "observe":
            return command_observe(
                settings, config_path, args.observability_config, args.mode,
                args.only, args.include_disabled
            )
        raise RuntimeError(f"Comando no implementado: {args.command}")
    except ReplicaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Ejecución cancelada.", file=sys.stderr)
        return 130
    except Exception as exc:
        logging.getLogger(__name__).exception("Error no controlado")
        print(f"ERROR NO CONTROLADO: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
