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
WHERE calidad_ciclo NOT IN ('ELEGIBLE','SIN_VENTA_FECHADA')
GROUP BY codigo_proyecto,calidad_ciclo;
SELECT * FROM analytics.v_absorcion_ventas_revision;

-- Cuadro listo para exportar o consumir desde Power BI.
SELECT periodo_mes,nombre_proyecto,stock_inicial,ingresos_mes,
       ventas_mes,stock_final,absorcion_mensual,unidades_revision
FROM analytics.v_absorcion_ventas_mensual
ORDER BY periodo_mes,nombre_proyecto;
