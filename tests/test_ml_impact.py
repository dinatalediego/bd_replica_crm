from decimal import Decimal
import unittest

from replica_cygnus.ml_impact import parse_rows


def rows(project="Torre Nápoles"):
    values = [
        ("1. Resumen comercial", "Meta Total Departamentos", 48, 270),
        ("1. Resumen comercial", "Valor Total Colocado", 41, 137),
        ("1. Resumen comercial", "Gap a Meta", 18, 133),
        ("4. Composición de ventas", "Valor Unidades Vendidas", 24, 82),
        ("4. Composición de ventas", "Valor Unidades Separadas", 17, 55),
        ("5. Stock Por vender ", "Valor Stock Disponible", 40, 133),
        ("5. Stock Por vender ", "Valor Unidades Disponible", 39, 130),
        ("5. Stock Por vender ", "Valor Unidades Bloqueadas", 1, 3),
    ]
    return [(block, indicator, project, str(value), "money_count", value, count)
            for block, indicator, value, count in values]


class ImpactImportTest(unittest.TestCase):
    def test_preserves_reported_gap_but_calculates_mathematical_gap(self):
        metrics, diagnostics = parse_rows(rows())
        self.assertEqual(len(metrics), 8)
        self.assertTrue(all(m.code == "NP" for m in metrics))
        self.assertEqual(diagnostics[0]["gap_math"], Decimal(7))
        self.assertEqual(diagnostics[0]["gap_difference"], Decimal(11))

    def test_rejects_unmapped_projects(self):
        with self.assertRaisesRegex(ValueError, "sin código CORE"):
            parse_rows(rows("Proyecto no mapeado"))

    def test_rejects_missing_source_indicators(self):
        with self.assertRaisesRegex(ValueError, "faltan indicadores"):
            parse_rows(rows()[:-2])

    def test_rejects_duplicate_metrics(self):
        data = rows()
        with self.assertRaisesRegex(ValueError, "duplicado"):
            parse_rows(data + [data[0]])

    def test_rejects_stock_that_cannot_reconcile(self):
        data = rows()
        data[-1] = (*data[-1][:5], 100, data[-1][6])
        with self.assertRaisesRegex(ValueError, "stock no concilia"):
            parse_rows(data)


if __name__ == "__main__":
    unittest.main()
