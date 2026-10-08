from pathlib import Path
import pytest
from replica_cygnus.econometric_datasets.imports import parse_rows


def file(tmp_path,body):
    p=tmp_path/'input.csv';p.write_text(body);return p


def test_market_release_requires_timezone(tmp_path):
    p=file(tmp_path,'mercado,indicador,periodo_mes,publicado_at,valor,unidad,fuente\nLIMA,tasa,2026-01-01,2026-02-01T10:00:00,5,pct,fuente\n')
    with pytest.raises(ValueError,match='zona horaria'): parse_rows('mercado',p)


def test_market_rejects_nonfinite(tmp_path):
    p=file(tmp_path,'mercado,indicador,periodo_mes,publicado_at,valor,unidad,fuente\nLIMA,tasa,2026-01-01,2026-02-01T10:00:00-05:00,NaN,pct,fuente\n')
    with pytest.raises(ValueError,match='no finito'): parse_rows('mercado',p)


def test_market_month_must_be_first_day(tmp_path):
    p=file(tmp_path,'mercado,indicador,periodo_mes,publicado_at,valor,unidad,fuente\nLIMA,tasa,2026-01-02,2026-02-01T10:00:00-05:00,5,pct,fuente\n')
    with pytest.raises(ValueError,match='primer día'): parse_rows('mercado',p)


def test_external_offer_cannot_claim_observed_quality(tmp_path):
    p=file(tmp_path,'codigo_unidad,codigo_proyecto,tipo_precio,fecha_referencia,disponible_desde,precio,moneda,area_total,descuento,fuente,clave_fuente,calidad\nA,P,LISTA,2024-01-01,2024-01-01T00:00:00-05:00,100000,PEN,50,,archivo,1,OBSERVADO\n')
    columns,rows=parse_rows('ofertas',p)
    assert dict(zip(columns,rows[0]))['calidad']=='IMPORTADO_DOCUMENTAL_PENDIENTE_AUDITORIA'


def test_missing_price_currency_is_rejected(tmp_path):
    p=file(tmp_path,'codigo_unidad,codigo_proyecto,tipo_precio,fecha_referencia,disponible_desde,precio,moneda,area_total,descuento,fuente,clave_fuente,calidad\nA,P,LISTA,2024-01-01,2024-01-01T00:00:00-05:00,100000,,50,,archivo,1,OBSERVADO\n')
    with pytest.raises(ValueError,match='moneda obligatorio'): parse_rows('ofertas',p)


def test_scheduled_step_after_core_and_sales_before_serving():
    root=Path(__file__).resolve().parents[1]
    # Inspect real generated steps without importing DB or connecting.
    import runpy
    module=runpy.run_path(str(root/'scripts/dw_refresh.py'),run_name='test_dw')
    steps=module['_steps']('hourly',True)
    names=[s.name for s in steps]
    assert names.index('03_core_commercial_refresh')<names.index('05_absorption_phase_b_incremental')<names.index('07b_econometric_datasets')<names.index('08_materialized_views')
    assert '--once-per-day' in steps[names.index('07b_econometric_datasets')].args
    assert '01_raw_sync' not in names
