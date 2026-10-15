-- Lectura local en medallio_dw. No modifica tablas ni reglas comerciales.
-- Cada fila de v_absorcion_ventas_revision es una UNIDAD actual; en la serie
-- mensual la misma unidad se cuenta otra vez en cada mes del proyecto.

-- 1. Alcance del bloqueo en el último run y cantidad de unidades por revisar.
SELECT c.project AS codigo_proyecto, c.stock AS stock_fuera_del_pronostico,
       count(DISTINCT u.codigo_unidad) AS unidades_distintas_en_revision
FROM analytics.v_commercial_forecast_coverage c
LEFT JOIN analytics.v_absorcion_ventas_revision u
  ON u.codigo_proyecto = c.project
WHERE c.status = 'QUARANTINED_REVIEW_UNITS'
GROUP BY c.project, c.stock
ORDER BY c.stock DESC, c.project;

-- 2. Identificar la unidad y TODAS las condiciones que podrían justificar
-- revisión. Nunca cambiar requiere_revision manualmente para liberar el modelo.
SELECT u.codigo_proyecto, u.nombre_proyecto, u.codigo_unidad, u.nombre_unidad,
       u.estado_comercial_actual, u.fecha_venta, u.ventas_elegibles,
       u.ciclos_revision, u.ultima_actualizacion_ciclos,
       (u.ventas_elegibles > 1) AS duplicidad_venta_vigente,
       (u.ciclos_revision > 0) AS ciclo_pendiente,
       (u.fecha_venta IS NULL AND lower(coalesce(u.estado_comercial_actual,'')) LIKE '%vendid%')
           AS vendida_sin_venta_validada
FROM analytics.v_absorcion_ventas_revision u
WHERE u.codigo_proyecto IN ('NP','SL','TZ')
ORDER BY u.codigo_proyecto, u.codigo_unidad;

-- 3. Evidencia documental de cada unidad. Una unidad puede tener varios ciclos.
-- No incluye nombres, documentos, emails ni teléfonos de clientes.
SELECT c.codigo_proyecto, c.codigo_unidad, c.codigo_proforma,
       c.calidad_ciclo, c.metodo_fecha_venta, c.fecha_de_minuta,
       c.fecha_firma_legacy, c.fecha_venta_documental, c.fecha_anulacion,
       c.reconciliation_status, c.observacion
FROM analytics.v_absorcion_ventas_ciclos c
JOIN analytics.v_absorcion_ventas_revision u
  ON u.codigo_unidad = c.codigo_unidad
WHERE u.codigo_proyecto IN ('NP','SL','TZ')
ORDER BY u.codigo_proyecto, u.codigo_unidad, c.codigo_proforma;
