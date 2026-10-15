let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = Text.Combine({
            "SELECT u.codigo_proyecto AS project, u.nombre_proyecto, u.codigo_unidad,",
            "u.nombre_unidad, u.estado_comercial_actual, u.fecha_venta,",
            "u.ventas_elegibles, u.ciclos_revision, u.ultima_actualizacion_ciclos,",
            "(u.ventas_elegibles > 1) AS duplicidad_venta_vigente,",
            "(u.ciclos_revision > 0) AS ciclo_pendiente,",
            "(u.fecha_venta IS NULL AND lower(coalesce(u.estado_comercial_actual,'')) LIKE '%vendid%') AS vendida_sin_venta_validada,",
            "c.calidades_ciclo, c.proformas,",
            "CASE WHEN u.ventas_elegibles > 1 THEN 'MULTIPLES_VENTAS_VIGENTES'",
            "WHEN u.ciclos_revision > 0 THEN 'CICLO_PENDIENTE'",
            "WHEN u.fecha_venta IS NULL AND lower(coalesce(u.estado_comercial_actual,'')) LIKE '%vendid%' THEN 'VENDIDA_SIN_FECHA_VALIDADA'",
            "ELSE 'REVISION' END AS motivo_principal",
            "FROM analytics.v_absorcion_ventas_revision u",
            "LEFT JOIN LATERAL (",
            " SELECT string_agg(DISTINCT c.calidad_ciclo, ', ' ORDER BY c.calidad_ciclo) AS calidades_ciclo,",
            " string_agg(DISTINCT c.codigo_proforma, ', ' ORDER BY c.codigo_proforma) AS proformas",
            " FROM analytics.v_absorcion_ventas_ciclos c WHERE c.codigo_unidad = u.codigo_unidad",
            ") c ON true"
        }, " ")]
    ),
    Types = Table.TransformColumnTypes(Source, {
        {"fecha_venta", type date},
        {"ultima_actualizacion_ciclos", type datetimezone},
        {"ventas_elegibles", Int64.Type},
        {"ciclos_revision", Int64.Type},
        {"duplicidad_venta_vigente", type logical},
        {"ciclo_pendiente", type logical},
        {"vendida_sin_venta_validada", type logical}
    })
in
    Types
