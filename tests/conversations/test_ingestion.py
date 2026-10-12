from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from replica_cygnus.conversations.extraction import extract_events, extract_linked_events
from replica_cygnus.conversations.parser import parse_export
from replica_cygnus.conversations.service import HistoricalExportChanged, validate_append_only
from scripts.dw_refresh import _steps


class ConversationIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "Chat de WhatsApp con Cygnus - Ventas.txt"

    def write(self, content: str):
        self.path.write_text(content, encoding="utf-8-sig")
        return parse_export(self.path)

    def test_multiline_sender_duplicate_and_append_only_contract(self):
        first = self.write(
            "1/3/25, 7:05\u202fp.\u202fm. - Nelly Román\nAsesora de ventas Cygnus: Salida Sialia\n2 visitas\n"
            "1/3/25, 7:06\u202fp.\u202fm. - Ana: Felicitaciones!\n"
            "1/3/25, 7:06\u202fp.\u202fm. - Ana: Felicitaciones!\n"
        )
        self.assertEqual(len(first), 3)
        self.assertEqual(first[0].sender, "Nelly Román Asesora de ventas Cygnus")
        self.assertEqual(first[0].sent_at, datetime(2025, 3, 1, 19, 5))
        self.assertNotEqual(first[1].message_id, first[2].message_id)
        previous = [m.message_id for m in first]
        self.assertEqual(validate_append_only(first, previous), [])

        appended = self.write(self.path.read_text(encoding="utf-8-sig") +
                              "2/3/25, 12:00\u202fa.\u202fm. - Ana: Cierre\n")
        self.assertEqual(len(validate_append_only(appended, previous)), 1)
        self.assertEqual(appended[-1].sent_at, datetime(2025, 3, 2, 0, 0))
        edited = self.write(self.path.read_text(encoding="utf-8-sig").replace("2 visitas", "3 visitas"))
        with self.assertRaises(HistoricalExportChanged):
            validate_append_only(edited, previous)

    def test_visit_date_multiple_projects_and_ambiguous_range(self):
        messages = self.write(
            "23/6/25, 8:00\u202fa.\u202fm. - Ana: Buen día, ayer estuve en feria\n"
            "20 a 22 visitas en Sialia\n"
            "Modena 1 visita\n"
        )
        reports = [e for e in extract_events(messages[0]) if e.event_type == "visita_reporte"]
        self.assertEqual(len(reports), 2)
        self.assertEqual([(e.project_name, e.count_min, e.count_max) for e in reports],
                         [("Sialia", 20, 22), ("Modena", 1, 1)])
        self.assertTrue(all(e.reported_date == date(2025, 6, 22) for e in reports))
        self.assertTrue(reports[0].review_required)

    def test_historical_weekday_and_cancellation_number_not_visits(self):
        messages = self.write(
            "28/4/25, 8:00\u202fa.\u202fm. - Ana: el sábado atendí 4 clientes en feria\n"
            "21/11/25, 4:00\u202fp.\u202fm. - Ana: Caída #3, dpto 303, fecha 15/11/25 cliente Feria\n"
            "10/10/25, 7:07\u202fp.\u202fm. - Ana: Salida Sialia no llegaron visitas\n"
        )
        first = extract_events(messages[0])[0]
        self.assertEqual((first.reported_date, first.count_min), (date(2025, 4, 26), 4))
        self.assertTrue(first.review_required)
        self.assertFalse(any(e.event_type == "visita_reporte" for e in extract_events(messages[1])))
        self.assertEqual([e.count_min for e in extract_events(messages[2])
                          if e.event_type == "visita_reporte"], [0])

    def test_reactions_link_to_sale_for_up_to_24_hours(self):
        messages = self.write(
            "5/3/25, 5:00\u202fp.\u202fm. - Ana: Separación Fenix dpto 1703\n"
            "5/3/25, 5:01\u202fp.\u202fm. - Beto: Felicitaciones Ana, más separaciones!\n"
            "6/3/25, 4:59\u202fp.\u202fm. - Carla: Bravo Ana por Fenix 1703!\n"
            "6/3/25, 5:02\u202fp.\u202fm. - Dani: Felicitaciones Ana!\n"
            "6/3/25, 5:03\u202fp.\u202fm. - Ana: Vamos equipo!\n"
            "6/3/25, 5:04\u202fp.\u202fm. - Eva: Una minuta más y llegamos\n"
        )
        events = extract_linked_events(messages)
        sales = [e for e in events if e.event_type == "separacion_anuncio"]
        reactions = [e for e in events if e.event_type == "celebracion"]
        self.assertEqual(len(sales), 1)
        self.assertEqual({e.message_id for e in reactions},
                         {messages[1].message_id, messages[2].message_id})
        self.assertTrue(all(e.related_event_id == sales[0].event_id for e in reactions))
        self.assertTrue(all(e.unit_code == "1703" for e in reactions))
        self.assertFalse(any(e.message_id in {messages[3].message_id, messages[4].message_id}
                             for e in reactions))
        self.assertFalse(any(e.event_type == "minuta_reporte" for e in events))

    def test_visit_number_does_not_require_venue_or_followup_message(self):
        messages = self.write(
            "22/6/25, 11:26\u202fa.\u202fm. - Ana: Ayer Nelly atendió aproximadamente 20 personas\n"
            "Luis unas 14\n"
            "22/6/25, 11:30\u202fa.\u202fm. - Eva: Ayer Nelly atendió aproximadamente 20 personas y Luis unas 14\n"
            "22/6/25, 11:45\u202fa.\u202fm. - Luis: Buenos días, ayer en promedio unos 15 atendí\n"
            "22/6/25, 12:00\u202fp.\u202fm. - Ana: Separación Fenix dpto 1703 cliente Carlos\n"
        )
        reports = [e for message in messages for e in extract_events(message)
                   if e.event_type == "visita_reporte"]
        self.assertEqual([(e.count_min, e.count_max) for e in reports],
                         [(20, 20), (14, 14), (20, 20), (14, 14), (15, 15)])
        self.assertTrue(all(e.reported_date == date(2025, 6, 21) for e in reports))
        self.assertTrue(all(e.venue_type is None and e.review_required for e in reports))

    def test_manual_only_includes_conversations_when_txt_exists(self):
        import scripts.dw_refresh as refresh
        original = refresh.ROOT
        refresh.ROOT = Path(self.temp.name)
        self.addCleanup(setattr, refresh, "ROOT", original)
        (refresh.ROOT / "conversaciones").mkdir()
        self.assertFalse(any("conversaciones" in step.name for step in _steps("hourly")))
        self.assertFalse(any("conversaciones" in step.name for step in _steps("manual")))
        (refresh.ROOT / "conversaciones" / "ventas.txt").write_text("contenido")
        names = [step.name for step in _steps("manual", local_only=True)]
        self.assertEqual(names[1:3], ["02a_conversaciones_schema", "02a_conversaciones_import"])
        self.assertFalse(any("conversaciones" in step.name for step in _steps("hourly")))


if __name__ == "__main__":
    unittest.main()
