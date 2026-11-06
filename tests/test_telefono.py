from telefono import enmascarar_numero, normalizar_numero, numero_parece_valido


def test_enmascarar_numero_deja_solo_los_ultimos_4_digitos():
    assert enmascarar_numero("573001112233") == "********2233"
    assert enmascarar_numero("") == "desconocido"
    assert enmascarar_numero("123") == "***"


def test_normalizar_numero_quita_mas_espacios_y_guiones():
    assert normalizar_numero("+57 300 111 2233") == "573001112233"
    assert normalizar_numero("57-300-111-2233") == "573001112233"
    assert normalizar_numero("573001112233") == "573001112233"
    assert normalizar_numero("") == ""


def test_numero_parece_valido_acepta_solo_digitos_de_longitud_razonable():
    assert numero_parece_valido("573001112233") is True  # 12 dígitos
    assert numero_parece_valido("1234567890") is True  # 10 dígitos (mínimo)
    assert numero_parece_valido("123456789012345") is True  # 15 dígitos (máximo)
    assert numero_parece_valido("12345") is False  # muy corto
    assert numero_parece_valido("1234567890123456") is False  # muy largo
    assert numero_parece_valido("57300111223a") is False  # no es solo dígitos
    assert numero_parece_valido("") is False
