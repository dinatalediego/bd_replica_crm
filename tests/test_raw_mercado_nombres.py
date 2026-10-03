import unittest

from replica_cygnus.raw_mercado_loader import _build_canonical_rows


TARGET = ["codigo", "nombre", "tipo_unidad", "codigo_proyecto", "id", "_etl_source_run_id"]


class RawMercadoNamesTest(unittest.TestCase):
    def test_blank_names_derive_unique_apartment_labels(self):
        rows = [
            {"codigo": "AMMA-T1-X02-25-2502", "nombre": "", "tipo_unidad": "Departamento", "codigo_proyecto": "Amma-TM", "id": "1"},
            {"codigo": "AMMA-T1-X02-9-902", "nombre": "  ", "tipo_unidad": "Departamento", "codigo_proyecto": "Amma-TM", "id": "2"},
        ]
        columns, payload = _build_canonical_rows(rows, TARGET, "run-id")
        names = [dict(zip(columns, values))["nombre"] for values in payload]
        self.assertEqual(names, ["Departamento 2502", "Departamento 902"])
        self.assertEqual(len(set(names)), len(rows))

    def test_supplied_name_and_non_numeric_code(self):
        rows = [
            {"codigo": "A-01", "nombre": "  Dpto. 01  ", "tipo_unidad": "Departamento", "id": "1"},
            {"codigo": "A-PENTHOUSE", "nombre": "", "tipo_unidad": "Departamento", "id": "2"},
        ]
        columns, payload = _build_canonical_rows(rows, TARGET, "run-id")
        self.assertEqual([dict(zip(columns, values))["nombre"] for values in payload],
                         ["Dpto. 01", "Departamento A-PENTHOUSE"])

    def test_duplicate_names_fail_before_replacing_table(self):
        rows = [
            {"codigo": "T1-101", "tipo_unidad": "Departamento", "id": "1"},
            {"codigo": "T2-101", "tipo_unidad": "Departamento", "id": "2"},
        ]
        with self.assertRaisesRegex(ValueError, "nombre duplicado"):
            _build_canonical_rows(rows, TARGET, "run-id")


if __name__ == "__main__":
    unittest.main()
