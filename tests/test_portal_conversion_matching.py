from portal_conversion.matching import PersonIdentity, normalize_dni, normalize_phone, score_match


def test_auto_identifier_is_not_dni() -> None:
    assert normalize_dni("auto-12345678") == ""
    assert normalize_dni("12345678") == "12345678"


def test_peru_phone_is_normalized() -> None:
    assert normalize_phone("+51 987 654 321") == "987654321"
    assert normalize_phone("987654321") == "987654321"


def test_exact_dni_is_confirmed_even_if_contact_is_missing() -> None:
    lead = PersonIdentity.build(dni="70856177", name="Diego Di Natale")
    buyer = PersonIdentity.build(dni="70856177", name="Diego Di Natale")
    result = score_match(lead, buyer)
    assert result.status == "CONFIRMADO"
    assert result.dni_score == 100
    assert result.automatic_conversion


def test_name_alone_never_becomes_automatic_conversion() -> None:
    lead = PersonIdentity.build(name="Maria Fernanda Salazar")
    buyer = PersonIdentity.build(name="Maria Fernanda Salazar")
    result = score_match(lead, buyer)
    assert result.status == "NO MATCH"
    assert not result.automatic_conversion


def test_name_plus_exact_contact_is_confirmed() -> None:
    lead = PersonIdentity.build(name="José Pérez Ramos", email="Jose.Perez@gmail.com")
    buyer = PersonIdentity.build(name="Jose Perez Ramos", email="jose.perez@gmail.com")
    result = score_match(lead, buyer)
    assert result.status == "CONFIRMADO"
    assert result.email_score == 100
