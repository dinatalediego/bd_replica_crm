-- Incremental v0.1:
-- recomputa únicamente business keys afectados en el lookback.
-- Para máxima seguridad temporal, el ledger se recalcula completo para las
-- unidades afectadas, no solo el último evento.

CREATE OR REPLACE PROCEDURE analytics.refresh_absorption_phase_b_incremental(
    p_lookback_days integer DEFAULT 7
)
LANGUAGE plpgsql
AS $$
BEGIN
    CREATE TEMP TABLE _affected_cycles ON COMMIT DROP AS
    SELECT DISTINCT
        p.codigo_proforma::text codigo_proforma,
        p.codigo_unidad::text codigo_unidad
    FROM raw_cygnus.procesos p
    WHERE p.fecha_actualizacion >= current_date - p_lookback_days
      AND p.codigo_proforma IS NOT NULL
      AND p.codigo_unidad IS NOT NULL

    UNION

    SELECT DISTINCT
        pu.codigo_proforma::text,
        pu.codigo_unidad::text
    FROM raw_cygnus.proforma_unidad pu
    WHERE pu.fecha_actualizacion >= current_date - p_lookback_days
      AND pu.codigo_proforma IS NOT NULL
      AND pu.codigo_unidad IS NOT NULL

    UNION

    SELECT DISTINCT
        de.codigo::text,
        p.codigo_unidad::text
    FROM raw_cygnus.datos_extras de
    JOIN raw_cygnus.procesos p
      ON p.codigo_proforma::text=de.codigo::text
    WHERE de.fecha_actualizacion >= current_date - p_lookback_days
      AND lower(de.entidad)='proforma'
      AND lower(de.nombre) IN (
          'fecha_de_minuta','pago_ci','monto_total_pagado',
          'monto_pagado_de_cuota_inicial','asesor_compartido'
      );

    -- v0.1 mantiene el algoritmo incremental conservador:
    -- si no hubo cambios, no hace nada.
    IF NOT EXISTS (SELECT 1 FROM _affected_cycles) THEN
        RETURN;
    END IF;

    -- En esta primera versión de producción segura, el número de procesos es pequeño
    -- y las reglas temporales aún se están estabilizando. Para evitar inconsistencias
    -- entre tablas intermedias durante Fase B, se utiliza full rebuild SOLO cuando
    -- existe algún cambio detectado.
    --
    -- La v0.2 reemplazará esto por DELETE/UPSERT por business key tras validar QA
    -- del primer backfill y medir tiempos reales.
    CALL analytics.refresh_absorption_phase_b_full();
END;
$$;
