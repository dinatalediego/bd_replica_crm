from __future__ import annotations

from typing import Iterable

import pandas as pd

from .service import _connect


def _query_df(sql: str, params: Iterable[object] | None = None) -> pd.DataFrame:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, list(params or []))
            rows = cur.fetchall()
            columns = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=columns)


def fetch_stock_matrix_data(projects: Iterable[str] | None = None) -> pd.DataFrame:
    """Lee exactamente la misma vista que alimenta el Excel de stock disponible."""
    where = ""
    params: list[str] = []
    if projects:
        clean = [str(p).strip() for p in projects if str(p).strip()]
        if clean:
            placeholders = ", ".join(["%s"] * len(clean))
            where = f" AND proyecto IN ({placeholders})"
            params.extend(clean)

    sql = f"""
        SELECT
            proyecto,
            tipo_unidad,
            unidad,
            nombre_tipologia,
            piso,
            area_total,
            precio_lista,
            discount_pct,
            precio_con_descuento,
            moneda,
            fecha_actualizacion_dato,
            esquema_fuente,
            unidad_fuente_key
        FROM analytics.v_stock_disponible_export
        WHERE tipo_unidad IN ('Departamento', 'Estacionamiento', 'Depósito')
        {where}
        ORDER BY proyecto, tipo_unidad, unidad
    """
    return _query_df(sql, params)


def fetch_stock_status_data() -> pd.DataFrame:
    """Inventario UI por estado comercial para los proyectos configurados.

    Conserva el contrato de precio/descuento del exportador, pero NO limita el
    universo a Disponible. La exportación a Excel continúa usando
    analytics.v_stock_disponible_export y, por tanto, sigue siendo sólo stock
    disponible.
    """
    sql = """
        WITH ranked AS (
            SELECT
                u.*,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(u.codigo_proyecto, u.nombre_proyecto), u.codigo
                    ORDER BY u.source_loaded_at DESC NULLS LAST,
                             CASE WHEN u.esquema_fuente = 'raw_cygnus' THEN 0 ELSE 1 END
                ) AS rn
            FROM core.v_unidades_fuentes u
            WHERE u.codigo IS NOT NULL
        ), normalizada AS (
            SELECT
                u.*,
                translate(upper(coalesce(u.nombre_proyecto, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS proyecto_norm,
                translate(upper(trim(coalesce(u.estado_comercial, ''))), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS estado_norm,
                translate(upper(trim(coalesce(u.tipo_unidad, ''))), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS tipo_norm
            FROM ranked u
            WHERE u.rn = 1
        ), reglas AS (
            SELECT *
            FROM analytics.stock_discount_rules
            WHERE active
              AND valid_from <= CURRENT_DATE
              AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
        )
        SELECT
            r.project_display_name AS proyecto,
            u.codigo_proyecto,
            u.codigo AS unidad,
            CASE
                WHEN u.tipo_norm LIKE '%ESTACION%' THEN 'Estacionamiento'
                WHEN u.tipo_norm LIKE '%DEPOSITO%' THEN 'Depósito'
                WHEN u.tipo_norm LIKE '%DEPART%'
                  OR u.tipo_norm LIKE '%FLAT%'
                  OR u.tipo_norm LIKE '%DUPLEX%'
                  OR u.tipo_norm LIKE '%TRIPLEX%'
                    THEN 'Departamento'
                ELSE initcap(lower(coalesce(u.tipo_unidad, 'Sin clasificar')))
            END AS tipo_unidad,
            u.nombre_tipologia,
            u.piso,
            u.area_total,
            u.estado_comercial,
            CASE
                WHEN u.estado_norm = 'DISPONIBLE' THEN 'Disponible'
                WHEN u.estado_norm = 'NO DISPONIBLE' THEN 'No disponible'
                WHEN u.estado_norm IN ('PROCESO DE SEPARACION', 'SEPARADO') THEN 'Separado'
                WHEN u.estado_norm IN ('PROCESO DE APROBACION', 'PROCESO DE VENTA', 'VENDIDO') THEN 'Vendido'
                WHEN u.estado_norm IN ('PROCESO DE ENTREGA', 'ENTREGADO') THEN 'Entregado'
                ELSE 'Sin clasificar'
            END AS estado_grupo,
            u.precio_lista,
            r.discount_pct,
            CASE
                WHEN u.precio_lista IS NULL THEN NULL
                ELSE round(u.precio_lista * (1 - r.discount_pct), 2)
            END AS precio_con_descuento,
            COALESCE(NULLIF(trim(u.moneda_precio_lista), ''), 'PEN') AS moneda,
            greatest(u.fecha_precio_actualizado, u.fecha_actualizacion, u.source_loaded_at::date) AS fecha_actualizacion_dato,
            u.esquema_fuente,
            u.unidad_fuente_key
        FROM normalizada u
        JOIN reglas r
          ON position(r.project_key in u.proyecto_norm) > 0
        WHERE
            u.tipo_norm LIKE '%ESTACION%'
            OR u.tipo_norm LIKE '%DEPOSITO%'
            OR u.tipo_norm LIKE '%DEPART%'
            OR u.tipo_norm LIKE '%FLAT%'
            OR u.tipo_norm LIKE '%DUPLEX%'
            OR u.tipo_norm LIKE '%TRIPLEX%'
        ORDER BY proyecto, estado_grupo, tipo_unidad, unidad
    """
    return _query_df(sql)


def fetch_apartment_units() -> pd.DataFrame:
    """Unidad vigente por código para la rama visual de departamentos.

    La capa se apoya en core.v_unidades_fuentes y deriva el flag_departamento
    con el mismo contrato semántico usado por analytics.unidades_powerbi.
    No exporta datos: solo abastece la interfaz.
    """
    sql = """
        WITH ranked AS (
            SELECT
                u.*,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(u.codigo_proyecto, u.nombre_proyecto), u.codigo
                    ORDER BY u.source_loaded_at DESC NULLS LAST,
                             CASE WHEN u.esquema_fuente = 'raw_cygnus' THEN 0 ELSE 1 END
                ) AS rn
            FROM core.v_unidades_fuentes u
            WHERE u.codigo IS NOT NULL
        ), depas AS (
            SELECT
                u.*,
                CASE
                    WHEN lower(trim(coalesce(u.tipo_unidad, ''))) IN (
                        'departamento flat',
                        'departamento duplex',
                        'departamento dúplex',
                        'departamento triplex',
                        'departamento tríplex'
                    ) THEN true
                    ELSE false
                END AS flag_departamento,
                translate(upper(coalesce(u.nombre_proyecto, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS proyecto_norm
            FROM ranked u
            WHERE u.rn = 1
        ), reglas AS (
            SELECT *
            FROM analytics.stock_discount_rules
            WHERE active
              AND valid_from <= CURRENT_DATE
              AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
        )
        SELECT
            COALESCE(NULLIF(trim(u.nombre_proyecto), ''), u.codigo_proyecto) AS proyecto,
            u.codigo_proyecto,
            u.codigo AS unidad,
            u.tipo_unidad,
            u.flag_departamento,
            u.nombre_tipologia,
            COALESCE(NULLIF(trim(u.tipologia_ubicacion), ''), RIGHT(trim(u.codigo), 2)) AS tipologia_ubicacion,
            u.piso,
            u.area_total,
            u.estado_comercial,
            u.estado_personalizado,
            u.precio_lista,
            u.precio_venta,
            u.precio_m2 AS precio_m2_origen,
            COALESCE(r.discount_pct, 0::numeric) AS discount_pct,
            CASE
                WHEN u.precio_lista IS NULL THEN NULL
                ELSE round(u.precio_lista * (1 - COALESCE(r.discount_pct, 0::numeric)), 2)
            END AS precio_con_descuento,
            COALESCE(NULLIF(trim(u.moneda_precio_lista), ''), 'PEN') AS moneda,
            greatest(u.fecha_precio_actualizado, u.fecha_actualizacion, u.source_loaded_at::date) AS fecha_actualizacion_dato,
            u.esquema_fuente,
            u.unidad_fuente_key
        FROM depas u
        LEFT JOIN reglas r
          ON position(r.project_key in u.proyecto_norm) > 0
        WHERE u.flag_departamento
        ORDER BY proyecto, piso, tipologia_ubicacion, unidad
    """
    return _query_df(sql)


def fetch_discount_rules() -> pd.DataFrame:
    return _query_df(
        """
        SELECT
            project_key,
            project_display_name,
            discount_pct,
            valid_from,
            valid_to,
            active,
            updated_at
        FROM analytics.stock_discount_rules
        ORDER BY project_display_name
        """
    )
