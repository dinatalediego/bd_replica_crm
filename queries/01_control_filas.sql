-- ============================================================
-- MEDALLIO DW - CONTROL DE FILAS
-- Base esperada: medallio_dw
-- Schema local: raw_cygnus
-- ============================================================

SELECT *
FROM (
    SELECT 'clientes_proyectos' AS tabla, COUNT(*) AS filas
    FROM raw_cygnus.clientes_proyectos

    UNION ALL

    SELECT 'interacciones', COUNT(*)
    FROM raw_cygnus.interacciones

    UNION ALL

    SELECT 'clientes', COUNT(*)
    FROM raw_cygnus.clientes

    UNION ALL

    SELECT 'procesos', COUNT(*)
    FROM raw_cygnus.procesos

    UNION ALL

    SELECT 'proformas', COUNT(*)
    FROM raw_cygnus.proformas

    UNION ALL

    SELECT 'unidades', COUNT(*)
    FROM raw_cygnus.unidades
) t
ORDER BY filas DESC;
