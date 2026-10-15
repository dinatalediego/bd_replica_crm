-- Ejecutar después del refresh normal. Ninguna consulta toca Redshift.
SELECT count(*) AS filas_mensuales, min(periodo_mes), max(periodo_mes),max(fecha_corte)
FROM analytics.v_absorcion_ventas_mensual;

-- Debe devolver cero filas.
SELECT * FROM analytics.v_absorcion_ventas_mensual
WHERE stock_inicial + ingresos_mes - ventas_mes <> stock_final
   OR stock_final < 0 OR stock_final > total_departamentos;

-- Revisar estos casos antes de considerar definitivo el cuadro.
SELECT * FROM analytics.v_absorcion_proyectos_sin_inicio;
SELECT codigo_proyecto,calidad_ciclo,count(*) AS ciclos
FROM analytics.v_absorcion_ventas_ciclos
WHERE calidad_ciclo NOT IN ('ELEGIBLE','SIN_VENTA_FECHADA','ANULADA_RETROSPECTIVAMENTE')
GROUP BY codigo_proyecto,calidad_ciclo;
SELECT * FROM analytics.v_absorcion_ventas_revision;

-- Cuadro listo para exportar o consumir desde Power BI.
SELECT periodo_mes,nombre_proyecto,stock_inicial,ingresos_mes,
       ventas_mes,stock_final,absorcion_mensual,unidades_revision
FROM analytics.v_absorcion_ventas_mensual
ORDER BY periodo_mes,nombre_proyecto;

-- Inicios ajustados y TODOS los casos con comentarios, incluidos los resueltos.
SELECT * FROM analytics.v_absorcion_inicio_proyecto ORDER BY nombre_proyecto;
SELECT * FROM analytics.v_absorcion_ventas_observaciones
ORDER BY codigo_proyecto,codigo_unidad,codigo_proforma;

-- Control duro: ambas consultas deben devolver cero filas.
SELECT * FROM analytics.v_absorcion_ventas_ciclos
WHERE calidad_ciclo='ELEGIBLE' AND metodo_fecha_venta='LEGACY_FECHA_FIRMA_PRE_2026'
  AND (fecha_separacion >= DATE '2026-01-01' OR fecha_separacion_raw >= DATE '2026-01-01');
SELECT * FROM analytics.v_absorcion_ventas_ciclos
WHERE calidad_ciclo='ELEGIBLE' AND fecha_anulacion IS NOT NULL;

-- Torre Nápoles: ambas consultas deben devolver cero filas.
SELECT a.codigo_unidad,u.codigo_subdivision
FROM analytics.v_absorcion_ventas_unidad a
JOIN core.dim_unidad u USING (codigo_unidad)
WHERE a.codigo_proyecto='NP' AND btrim(u.codigo_subdivision) IS DISTINCT FROM 'NP-A';
SELECT c.codigo_unidad,u.codigo_subdivision
FROM analytics.v_absorcion_ventas_ciclos c
JOIN core.dim_unidad u USING (codigo_unidad)
WHERE u.codigo_proyecto='NP' AND btrim(u.codigo_subdivision) IS DISTINCT FROM 'NP-A';

-- Comparar universo original con universo habilitado; RAW/CORE permanecen completos.
SELECT codigo_subdivision,count(*) AS unidades_originales
FROM core.dim_unidad WHERE codigo_proyecto='NP'
GROUP BY codigo_subdivision ORDER BY codigo_subdivision;
