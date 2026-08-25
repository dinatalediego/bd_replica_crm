from pathlib import Path

import pandas as pd
import pytest

from mercado_ingestion.config import MarketSource
from mercado_ingestion.loader import DataQualityError, normalize_header, read_and_prepare


SOURCE = MarketSource(
    source_id="amma_torre_marsano",
    empresa_fuente="Amma",
    codigo_proyecto="AMMA-TM",
    nombre_proyecto="Torre Marsano",
    sheet_name="Hoja1",
    header_row=2,
)


def test_normalize_header() -> None:
    assert normalize_header("Área de venta (m2)") == "area_de_venta_m2"


def test_reads_second_row_as_header(tmp_path: Path) -> None:
    columns = [
        "codigo_unidad", "torre", "tipo_unidad", "tipologia", "nro_inmueble",
        "piso", "vista", "area_techada", "area_libre", "area_venta",
        "dormitorios", "moneda", "precio_lista", "precio_venta", "pxm2",
        "fecha_separacion", "fecha_venta", "estado",
        "estado_comercial_original", "referido",
    ]
    data = pd.DataFrame(
        [["U-1", "T1", "Departamento", "X01", 101, 1, "Externa", 50, 0, 50, 2,
          "SOLES", 300000, 290000, 5800, None, None, "DISPONIBLE", "DISPONIBLE", None]],
        columns=columns,
    )
    path = tmp_path / "source.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([["descripción"] * len(columns)]).to_excel(
            writer, sheet_name="Hoja1", index=False, header=False
        )
        data.to_excel(writer, sheet_name="Hoja1", index=False, startrow=1)

    prepared = read_and_prepare(path, SOURCE)
    assert len(prepared.frame) == 1
    assert prepared.frame.iloc[0]["codigo_unidad"] == "U-1"
    assert prepared.frame.iloc[0]["numero_inmueble"] == "101"
    assert prepared.frame.iloc[0]["fila_origen"] == 3


def test_rejects_duplicate_unit_codes(tmp_path: Path) -> None:
    columns = [
        "codigo_unidad", "torre", "tipo_unidad", "tipologia", "nro_inmueble",
        "piso", "vista", "area_techada", "area_libre", "area_venta",
        "dormitorios", "moneda", "precio_lista", "precio_venta", "pxm2",
        "fecha_separacion", "fecha_venta", "estado",
        "estado_comercial_original", "referido",
    ]
    row = ["U-1", "T1", "Departamento", "X01", 101, 1, "Externa", 50, 0, 50, 2,
           "SOLES", 300000, 290000, 5800, None, None, "DISPONIBLE", "DISPONIBLE", None]
    path = tmp_path / "duplicate.csv"
    pd.DataFrame([row, row], columns=columns).to_csv(path, index=False)

    csv_source = MarketSource(**{**SOURCE.__dict__, "sheet_name": None, "header_row": 1})
    with pytest.raises(DataQualityError, match="duplicados"):
        read_and_prepare(path, csv_source)

