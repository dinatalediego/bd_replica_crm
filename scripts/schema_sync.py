from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


@dataclass(frozen=True)
class SchemaComponent:
    name: str
    files: tuple[str, ...]
    expected_relations: tuple[str, ...] = ()
    expected_procedures: tuple[str, ...] = ()


COMPONENTS: tuple[SchemaComponent, ...] = (
    SchemaComponent(
        name="core_commercial",
        files=("sql/init_core_commercial.sql",),
        expected_relations=("core.dim_proyecto", "core.dim_unidad"),
    ),
    SchemaComponent(
        name="absorption_phase_b",
        files=(
            "sql/20_absorption_phase_b/00_prerequisites.sql",
            "sql/20_absorption_phase_b/01_control_and_functions.sql",
            "sql/20_absorption_phase_b/02_tables.sql",
            "sql/20_absorption_phase_b/04_qa.sql",
            "sql/20_absorption_phase_b/03_refresh_full.sql",
            "sql/20_absorption_phase_b/03b_sale_date_pago_ci.sql",
            "sql/20_absorption_phase_b/03c_pago_ci_quality_override.sql",
            "sql/20_absorption_phase_b/05_incremental.sql",
        ),
        expected_relations=("analytics.int_ciclo_comercial_unidad",),
        expected_procedures=(
            "analytics.refresh_absorption_phase_b_incremental(integer)",
            "analytics.run_sale_date_pago_ci_qa()",
        ),
    ),
    SchemaComponent(
        name="core_commercial_lifecycle",
        files=("sql/init_core_commercial_lifecycle.sql",),
        expected_relations=(
            "core.fact_ciclo_comercial_unidad",
            "core.v_ciclo_comercial_health",
        ),
    ),
    SchemaComponent(
        name="unidades_powerbi",
        files=("sql/init_unidades_powerbi.sql",),
        expected_relations=("analytics.unidades_powerbi",),
    ),
    SchemaComponent(
        name="unidades_multifuente",
        files=(
            "sql/40_unidades_multifuente/00_add_tipologia_ubicacion.sql",
            "sql/40_unidades_multifuente/01_v_unidades_fuentes.sql",
            "sql/40_unidades_multifuente/02_market_lifecycle_inferido.sql",
            "sql/40_unidades_multifuente/03_analytics_comparativo.sql",
            "sql/40_unidades_multifuente/04_core_commercial_multifuente.sql",
        ),
        expected_relations=(
            "core.v_unidades_fuentes",
            "core.v_unidad_comercial_multifuente",
            "analytics_compare.v_powerbi_unidad_actual",
            "analytics_compare.v_powerbi_proyecto_actual",
        ),
    ),
    SchemaComponent(
        name="observability",
        files=("sql/init_observability.sql",),
        expected_relations=(
            "observability.asset_registry",
            "observability.asset_snapshots",
            "observability.quality_checks",
        ),
    ),
)


def _ensure_registry(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE SCHEMA IF NOT EXISTS etl_control;

            CREATE TABLE IF NOT EXISTS etl_control.schema_migrations (
                component_name  text PRIMARY KEY,
                checksum        text NOT NULL,
                status          text NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
                files           text[] NOT NULL DEFAULT ARRAY[]::text[],
                applied_at      timestamptz,
                checked_at      timestamptz NOT NULL DEFAULT now(),
                last_error      text
            );
            """
        )
    conn.commit()


def _checksum(root: Path, component: SchemaComponent) -> str:
    digest = hashlib.sha256()
    for relative in component.files:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _current_record(conn, component_name: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT checksum, status
            FROM etl_control.schema_migrations
            WHERE component_name = %s
            """,
            (component_name,),
        )
        return cur.fetchone()


def _objects_exist(conn, component: SchemaComponent) -> tuple[bool, list[str]]:
    missing: list[str] = []
    with conn.cursor() as cur:
        for relation in component.expected_relations:
            cur.execute("SELECT to_regclass(%s)", (relation,))
            if cur.fetchone()[0] is None:
                missing.append(relation)

        for procedure in component.expected_procedures:
            cur.execute("SELECT to_regprocedure(%s)", (procedure,))
            if cur.fetchone()[0] is None:
                missing.append(procedure)

    return not missing, missing


def _record_failure(conn, component: SchemaComponent, checksum: str, exc: Exception) -> None:
    message = f"{type(exc).__name__}: {exc}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_control.schema_migrations (
                component_name, checksum, status, files, applied_at, checked_at, last_error
            )
            VALUES (%s, %s, 'FAILED', %s, NULL, now(), %s)
            ON CONFLICT (component_name) DO UPDATE
            SET checksum = EXCLUDED.checksum,
                status = EXCLUDED.status,
                files = EXCLUDED.files,
                checked_at = now(),
                last_error = EXCLUDED.last_error
            """,
            (component.name, checksum, list(component.files), message[:4000]),
        )
    conn.commit()


def _apply_component(conn, root: Path, component: SchemaComponent, force: bool) -> str:
    checksum = _checksum(root, component)
    record = _current_record(conn, component.name)
    healthy, missing = _objects_exist(conn, component)

    if (
        not force
        and record is not None
        and record[0] == checksum
        and record[1] == "SUCCESS"
        and healthy
    ):
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE etl_control.schema_migrations
                SET checked_at = now(), last_error = NULL
                WHERE component_name = %s
                """,
                (component.name,),
            )
        conn.commit()
        print(f"[SCHEMA][OK] {component.name}: sin cambios; objetos presentes.")
        return "SKIPPED"

    reason = "force" if force else "cambio/no instalado"
    if not healthy:
        reason = "objetos faltantes: " + ", ".join(missing)

    print(f"[SCHEMA][APPLY] {component.name} ({reason})")
    try:
        with conn.cursor() as cur:
            for relative in component.files:
                print(f"  [SQL] {relative}")
                sql_text = (root / relative).read_text(encoding="utf-8")
                cur.execute(sql_text, prepare=False)

            cur.execute(
                """
                INSERT INTO etl_control.schema_migrations (
                    component_name, checksum, status, files, applied_at, checked_at, last_error
                )
                VALUES (%s, %s, 'SUCCESS', %s, now(), now(), NULL)
                ON CONFLICT (component_name) DO UPDATE
                SET checksum = EXCLUDED.checksum,
                    status = EXCLUDED.status,
                    files = EXCLUDED.files,
                    applied_at = now(),
                    checked_at = now(),
                    last_error = NULL
                """,
                (component.name, checksum, list(component.files)),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _record_failure(conn, component, checksum, exc)
        raise

    healthy_after, missing_after = _objects_exist(conn, component)
    if not healthy_after:
        exc = RuntimeError(
            f"{component.name} aplicado pero faltan objetos esperados: {', '.join(missing_after)}"
        )
        _record_failure(conn, component, checksum, exc)
        raise exc

    print(f"[SCHEMA][OK] {component.name}: aplicado y verificado.")
    return "APPLIED"


def _print_status(conn, root: Path, components: tuple[SchemaComponent, ...]) -> int:
    _ensure_registry(conn)
    failures = 0
    for component in components:
        checksum = _checksum(root, component)
        record = _current_record(conn, component.name)
        healthy, missing = _objects_exist(conn, component)

        if record is None:
            state = "NOT_APPLIED"
        elif record[1] != "SUCCESS":
            state = "FAILED"
        elif record[0] != checksum:
            state = "CODE_CHANGED"
        elif not healthy:
            state = "DRIFT"
        else:
            state = "OK"

        if state != "OK":
            failures += 1
        suffix = f" | missing={','.join(missing)}" if missing else ""
        print(f"{component.name:28} {state}{suffix}")

    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sincroniza definiciones SQL del DW con el código del repositorio. "
            "Solo reaplica componentes cuyo checksum cambió o cuyos objetos faltan."
        )
    )
    parser.add_argument("--force", action="store_true", help="Reaplica todos los componentes.")
    parser.add_argument("--status", action="store_true", help="Solo muestra estado de esquema.")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Componente a procesar; puede repetirse.",
    )
    args = parser.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    selected = COMPONENTS
    if args.only:
        requested = set(args.only)
        selected = tuple(c for c in COMPONENTS if c.name in requested)
        unknown = requested - {c.name for c in COMPONENTS}
        if unknown:
            raise SystemExit(f"Componentes desconocidos: {', '.join(sorted(unknown))}")

    with connect_postgres(settings) as conn:
        _ensure_registry(conn)

        if args.status:
            return _print_status(conn, root, selected)

        applied = 0
        skipped = 0
        for component in selected:
            result = _apply_component(conn, root, component, force=args.force)
            applied += result == "APPLIED"
            skipped += result == "SKIPPED"

    print(f"[SCHEMA] completado: applied={applied}, unchanged={skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
