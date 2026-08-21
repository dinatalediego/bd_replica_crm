-- Commercial sale-date correction after source profiling.
--
-- Source evidence established on 2026-08-18:
--   * datos_extras.nombre='pago_ci' is NOT a date. Its current known value is
--     the marker text 'Pagó cuota inicial (Minuta)'.
--   * datos_extras.nombre='fecha_de_minuta' is the date field used by the
--     legacy Power Query as Fecha_PagoCI_pm / effective commercial sale date.
--   * the two fields are not required to coexist; marker-only rows are valid
--     evidence of conversion but have missing conversion date and therefore
--     must never be interpreted as "not paid" by a risk model.
--
-- The original Phase-B refresh already implements the authoritative dated rule:
--   fecha_venta = COALESCE(
--       fecha_de_minuta,
--       CASE WHEN fecha_separacion < DATE '2026-01-01'
--            THEN fecha_proceso_venta END
--   )
-- and from 2026 onward the Venta process date is only process closure.
--
-- An earlier branch revision temporarily wrapped refresh_absorption_phase_b_full
-- and attempted to parse pago_ci as a date. This migration safely removes that
-- mistaken override on databases where it was already installed and restores
-- the original Phase-B procedure as the authoritative implementation.

DO $$
BEGIN
    IF to_regprocedure('analytics.refresh_absorption_phase_b_full_base()') IS NOT NULL THEN
        DROP PROCEDURE IF EXISTS analytics.refresh_absorption_phase_b_full();
        ALTER PROCEDURE analytics.refresh_absorption_phase_b_full_base()
            RENAME TO refresh_absorption_phase_b_full;
    END IF;
END
$$;

-- Remove the obsolete mutating procedure if a previous local install created it.
DROP PROCEDURE IF EXISTS analytics.apply_sale_date_pago_ci_rule();

-- Compatibility columns created by the experimental implementation are kept in
-- place so existing local schemas do not require destructive migration. They are
-- no longer authoritative. CORE exposes fecha_de_minuta as fecha_pago_ci.
COMMENT ON COLUMN analytics.int_ciclo_comercial_unidad.fecha_pago_ci IS
    'Deprecated physical compatibility column. Authoritative fecha_pago_ci is fecha_de_minuta via CORE.';
COMMENT ON COLUMN analytics.int_ciclo_comercial_unidad.datos_extras_pago_ci_id IS
    'Deprecated compatibility column. pago_ci is a marker, not the dated conversion source.';
