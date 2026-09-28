from datetime import datetime

from portal_conversion.matching import PersonIdentity
from scripts.refresh_portal_conversion import (
    LeadRow,
    _apply_origin_priority,
    _assign_unique_conversions,
    _conversion_key,
    _identity_from_client,
)


def _lead(uid: str, source: str, date: datetime, project: str = "NP") -> LeadRow:
    identity = PersonIdentity.build(
        dni="70856177",
        name="Diego Di Natale",
        phone="+51 987654321",
        email="diego@example.com",
    )
    return LeadRow(
        data={
            "lead_uid": uid,
            "fuente_lead": source,
            "fecha_creacion": date,
            "codigo_proyecto": project,
            "duplicado_en_origen": False,
            "lead_origen_uid": None,
            "incluir_en_kpi": True,
        },
        identity=identity,
    )


def test_origin_wins_when_same_lead_is_in_both_sources() -> None:
    origin = _lead("ORIGEN:1", "ORIGEN", datetime(2026, 1, 10))
    current = _lead("MEDIO_ACTUAL:8", "MEDIO_ACTUAL", datetime(2026, 1, 11))

    _apply_origin_priority([origin, current])

    assert origin.data["incluir_en_kpi"] is True
    assert current.data["duplicado_en_origen"] is True
    assert current.data["incluir_en_kpi"] is False
    assert current.data["lead_origen_uid"] == "ORIGEN:1"


def test_same_person_different_project_is_not_suppressed_as_same_lead() -> None:
    origin = _lead("ORIGEN:1", "ORIGEN", datetime(2026, 1, 10), project="NP")
    current = _lead("MEDIO_ACTUAL:8", "MEDIO_ACTUAL", datetime(2026, 1, 11), project="MD")

    _apply_origin_priority([origin, current])

    assert current.data["duplicado_en_origen"] is False
    assert current.data["incluir_en_kpi"] is True


def test_conversion_key_prefers_valid_dni() -> None:
    identity = PersonIdentity.build(
        dni="70856177",
        email="diego@example.com",
        phone="987654321",
    )
    key = _conversion_key(identity, {"proceso_id": "1", "codigo_proforma": "P1"})
    assert key == "dni:70856177"


def test_one_person_conversion_is_attributed_only_once() -> None:
    early = _lead("ORIGEN:1", "ORIGEN", datetime(2026, 1, 10))
    later = _lead("ORIGEN:2", "ORIGEN", datetime(2026, 1, 20))
    matches = [
        {
            "lead_uid": "ORIGEN:1",
            "conversion_key": "dni:70856177",
            "conversion_elegible": True,
            "conversion_atribuida": False,
            "estado_match": "CONFIRMADO",
            "score_global": 100.0,
        },
        {
            "lead_uid": "ORIGEN:2",
            "conversion_key": "dni:70856177",
            "conversion_elegible": True,
            "conversion_atribuida": False,
            "estado_match": "CONFIRMADO",
            "score_global": 100.0,
        },
    ]

    _assign_unique_conversions([early, later], matches)

    assert sum(bool(match["conversion_atribuida"]) for match in matches) == 1
    assert matches[0]["conversion_atribuida"] is True


def test_client_document_recovers_real_dni_from_auto_source_document() -> None:
    identity = _identity_from_client(
        "auto-123456789",
        {
            "source_id": "42",
            "documento": "70856177",
            "numero_documento": None,
            "dq_nombre_cliente": "Diego Di Natale",
            "nombres": "Diego",
            "apellidos": "Di Natale",
            "dq_celular_limpio": "987654321",
            "dq_email_limpio": "diego@example.com",
        },
    )

    assert identity.source_document == "auto-123456789"
    assert identity.dni == "70856177"
