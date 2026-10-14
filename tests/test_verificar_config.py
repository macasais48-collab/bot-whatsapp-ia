from verificar_config import VARIABLES_ESPERADAS, generar_reporte


def test_reporte_no_contiene_ningun_valor_real():
    valores_falsos = {
        "PROVEEDOR_IA": "claude",
        "ANTHROPIC_API_KEY": "sk-ant-valor-super-secreto-de-prueba",
        "MODELO_IA": "",
        "MAX_TURNOS_HISTORIAL": "6",
        "WHATSAPP_TOKEN": "token-secreto-de-prueba-xyz",
        "WHATSAPP_PHONE_NUMBER_ID": "",
        "WHATSAPP_VERIFY_TOKEN": "verificacion-secreta-de-prueba",
        "META_APP_SECRET": "secreto-de-prueba-app",
        "GRAPH_API_VERSION": "v26.0",
        "WHATSAPP_WABA_ID": "waba-id-de-prueba-123",
        "PUERTO": "8000",
    }

    reporte = generar_reporte(valores_falsos)

    for nombre, valor in valores_falsos.items():
        if valor:
            assert valor not in reporte


def test_reporte_marca_con_valor_o_vacio_segun_corresponda():
    valores_falsos = {
        "PROVEEDOR_IA": "claude",
        "ANTHROPIC_API_KEY": "sk-ant-valor-super-secreto-de-prueba",
        "MODELO_IA": "",
        "GRAPH_API_VERSION": "v26.0",
    }

    reporte = generar_reporte(valores_falsos)

    assert "PROVEEDOR_IA: con valor" in reporte
    assert "ANTHROPIC_API_KEY: con valor" in reporte
    assert "MODELO_IA: VACÍO" in reporte
    assert "GRAPH_API_VERSION: con valor" in reporte


def test_valor_formado_solo_por_espacios_se_reporta_como_vacio():
    reporte = generar_reporte({"META_APP_SECRET": "   \n"})

    assert "META_APP_SECRET: VACÍO" in reporte


def test_variable_faltante_se_reporta_como_vacio():
    reporte = generar_reporte({})

    for nombre in VARIABLES_ESPERADAS:
        assert f"{nombre}: VACÍO" in reporte


def test_el_reporte_incluye_todas_las_variables_esperadas():
    reporte = generar_reporte({})

    for nombre in VARIABLES_ESPERADAS:
        assert nombre in reporte
