from env import obtener_env


def test_obtener_env_quita_espacios_y_saltos_de_linea(monkeypatch):
    monkeypatch.setenv("ALGUNA_VAR_DE_PRUEBA", "  valor con espacios \n")
    assert obtener_env("ALGUNA_VAR_DE_PRUEBA") == "valor con espacios"


def test_obtener_env_devuelve_none_si_no_existe(monkeypatch):
    monkeypatch.delenv("ALGUNA_VAR_DE_PRUEBA", raising=False)
    assert obtener_env("ALGUNA_VAR_DE_PRUEBA") is None


def test_obtener_env_usa_valor_por_defecto_si_no_existe(monkeypatch):
    monkeypatch.delenv("ALGUNA_VAR_DE_PRUEBA", raising=False)
    assert obtener_env("ALGUNA_VAR_DE_PRUEBA", "defecto") == "defecto"


def test_obtener_env_tambien_recorta_el_valor_por_defecto(monkeypatch):
    monkeypatch.delenv("ALGUNA_VAR_DE_PRUEBA", raising=False)
    assert obtener_env("ALGUNA_VAR_DE_PRUEBA", "  defecto  ") == "defecto"
