from __future__ import annotations

from pathlib import Path

from psycopg import Connection


def ensure_core_commercial(conn: Connection, project_root: Path) -> None:
    """Create/upgrade the governed commercial CORE objects from versioned SQL."""
    sql_path = project_root / "sql" / "init_core_commercial.sql"
    sql_text = sql_path.read_text(encoding="utf-8")
    with conn.cursor() as cursor:
        cursor.execute(sql_text, prepare=False)
    conn.commit()


def refresh_core_commercial(conn: Connection, project_root: Path) -> dict[str, int]:
    """Rebuild and reconcile the current-state commercial CORE from raw_cygnus."""
    ensure_core_commercial(conn, project_root)

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE TABLE
                    core.dim_unidad,
                    core.dim_proyecto
                """
            )

            cursor.execute(
                """
                INSERT INTO core.dim_proyecto (
                    proyecto_id,
                    codigo_proyecto,
                    nombre_proyecto,
                    direccion,
                    fecha_estimacion,
                    fecha_real,
                    fecha_inicio_venta,
                    latitud,
                    longitud,
                    pais,
                    departamento,
                    provincia,
                    distrito,
                    usuario_creador,
                    username,
                    tipo_proyecto,
                    estado_construccion,
                    total_unidades_reportado,
                    unidades_vendidas_reportado,
                    moneda,
                    codigo_externo,
                    tasa_interes_mensual,
                    banco_promotor,
                    fecha_actualizacion_origen,
                    razon_social,
                    direccion_razon_social,
                    ruc_razon_social,
                    source_loaded_at,
                    source_run_id,
                    core_loaded_at
                )
                SELECT
                    id,
                    TRIM(codigo),
                    nombre,
                    direccion,
                    fecha_estimacion,
                    fecha_real,
                    fecha_inicio_venta,
                    latitud,
                    longitud,
                    pais,
                    departamento,
                    provincia,
                    distrito,
                    usuario_creador,
                    username,
                    tipo_proyecto,
                    estado_construccion,
                    total_unidades,
                    unidades_vendidas,
                    moneda,
                    codigo_externo,
                    tasa_interes_mensual,
                    banco_promotor,
                    fecha_actualizacion,
                    razon_social,
                    direccion_razon_social,
                    ruc_razon_social,
                    _etl_loaded_at,
                    _etl_source_run_id,
                    now()
                FROM raw_cygnus.proyectos
                """
            )

            cursor.execute(
                """
                INSERT INTO core.dim_unidad (
                    unidad_id,
                    codigo_unidad,
                    codigo_proyecto,
                    nombre_unidad,
                    nombre_proyecto_origen,
                    codigo_subdivision,
                    nombre_subdivision,
                    tipo_unidad,
                    piso,
                    estado_construccion,
                    nombre_tipologia,
                    tipologia_ubicacion,
                    total_habitaciones,
                    total_banos,
                    area_libre,
                    area_techada,
                    area_total,
                    estado_comercial,
                    estado_personalizado,
                    codigo_proforma_actual,
                    precio_lista_actual,
                    precio_base_proforma_actual,
                    descuento_venta_actual,
                    precio_venta_actual,
                    precio_m2_actual,
                    fecha_reserva_actual,
                    fecha_separacion_actual,
                    fecha_venta_actual,
                    fecha_entrega,
                    fecha_inicio_independizacion,
                    fecha_fin_independizacion,
                    modalidad_contrato,
                    codigo_externo,
                    fecha_precio_actualizado,
                    moneda_precio_lista,
                    moneda_venta,
                    vcto_garantia_estructural,
                    vcto_garantia_acabados,
                    vcto_garantia_comercial,
                    padre_id,
                    fecha_actualizacion_origen,
                    fecha_estimada_entrega,
                    source_loaded_at,
                    source_run_id,
                    core_loaded_at
                )
                SELECT
                    id,
                    TRIM(codigo),
                    TRIM(codigo_proyecto),
                    nombre,
                    nombre_proyecto,
                    codigo_subdivision,
                    nombre_subdivision,
                    tipo_unidad,
                    piso,
                    estado_construccion,
                    nombre_tipologia,
                    CASE
                        WHEN NULLIF(TRIM(codigo), '') IS NULL THEN NULL
                        ELSE RIGHT(TRIM(codigo), 2)
                    END,
                    total_habitaciones,
                    total_banos,
                    area_libre,
                    area_techada,
                    area_total,
                    estado_comercial,
                    estado_personalizado,
                    codigo_proforma,
                    precio_lista,
                    precio_base_proforma,
                    descuento_venta,
                    precio_venta,
                    precio_m2,
                    fecha_reserva,
                    fecha_separacion,
                    fecha_venta,
                    fecha_entrega,
                    fecha_inicio_independizacion,
                    fecha_fin_independizacion,
                    modalidad_contrato,
                    codigo_externo,
                    fecha_precio_actualizado,
                    moneda_precio_lista,
                    moneda_venta,
                    vcto_garantia_estructural,
                    vcto_garantia_acabados,
                    vcto_garantia_comercial,
                    padre_id,
                    fecha_actualizacion,
                    fecha_estimada_entrega,
                    _etl_loaded_at,
                    _etl_source_run_id,
                    now()
                FROM raw_cygnus.unidades
                """
            )

            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM raw_cygnus.proyectos),
                    (SELECT COUNT(*) FROM core.dim_proyecto),
                    (SELECT COUNT(*) FROM raw_cygnus.unidades),
                    (SELECT COUNT(*) FROM core.dim_unidad)
                """
            )
            raw_proyectos, core_proyectos, raw_unidades, core_unidades = cursor.fetchone()

            if raw_proyectos != core_proyectos:
                raise RuntimeError(
                    f"Reconciliación fallida proyectos: RAW={raw_proyectos}, CORE={core_proyectos}"
                )
            if raw_unidades != core_unidades:
                raise RuntimeError(
                    f"Reconciliación fallida unidades: RAW={raw_unidades}, CORE={core_unidades}"
                )

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT
                        p.codigo_proyecto,
                        p.total_unidades_reportado,
                        COUNT(u.unidad_id) AS unidades_core
                    FROM core.dim_proyecto p
                    LEFT JOIN core.dim_unidad u USING (codigo_proyecto)
                    GROUP BY p.codigo_proyecto, p.total_unidades_reportado
                    HAVING COUNT(u.unidad_id) <> p.total_unidades_reportado
                ) AS diferencias
                """
            )
            proyectos_con_diferencia = int(cursor.fetchone()[0])

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM core.dim_unidad
                WHERE NULLIF(TRIM(codigo_unidad), '') IS NOT NULL
                  AND tipologia_ubicacion IS DISTINCT FROM RIGHT(TRIM(codigo_unidad), 2)
                """
            )
            tipologia_ubicacion_inconsistente = int(cursor.fetchone()[0])

            if tipologia_ubicacion_inconsistente:
                raise RuntimeError(
                    "Reconciliación fallida tipologia_ubicacion: "
                    f"{tipologia_ubicacion_inconsistente} filas inconsistentes"
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "raw_proyectos": int(raw_proyectos),
        "core_proyectos": int(core_proyectos),
        "raw_unidades": int(raw_unidades),
        "core_unidades": int(core_unidades),
        "proyectos_con_diferencia": proyectos_con_diferencia,
        "tipologia_ubicacion_inconsistente": tipologia_ubicacion_inconsistente,
    }


def core_status(conn: Connection) -> dict[str, int]:
    """Return minimal certified CORE health counts."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM core.dim_proyecto),
                (SELECT COUNT(*) FROM core.dim_unidad),
                (
                    SELECT COUNT(*)
                    FROM core.dim_unidad u
                    LEFT JOIN core.dim_proyecto p USING (codigo_proyecto)
                    WHERE p.proyecto_id IS NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM core.dim_unidad
                    WHERE NULLIF(TRIM(codigo_unidad), '') IS NOT NULL
                      AND tipologia_ubicacion IS DISTINCT FROM RIGHT(TRIM(codigo_unidad), 2)
                )
            """
        )
        proyectos, unidades, huerfanas, tipologia_inconsistente = cursor.fetchone()

    return {
        "proyectos": int(proyectos),
        "unidades": int(unidades),
        "unidades_huerfanas": int(huerfanas),
        "tipologia_ubicacion_inconsistente": int(tipologia_inconsistente),
    }
