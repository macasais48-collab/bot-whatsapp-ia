import pytest

from llm import crear_proveedor_ia


def test_proveedor_ia_invalido_no_filtra_su_valor_en_el_error(monkeypatch):
    valor_secreto = "sk-ant-usr-valor-que-no-deberia-aparecer-en-el-error"
    monkeypatch.setenv("PROVEEDOR_IA", valor_secreto)

    with pytest.raises(ValueError) as info:
        crear_proveedor_ia()

    assert valor_secreto not in str(info.value)
    assert str(info.value) == "PROVEEDOR_IA no es válido. Valores permitidos: claude, openai."
