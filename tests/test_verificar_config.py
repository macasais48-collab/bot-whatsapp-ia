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


def test_perfil_negocio_se_reporta_sin_mostrar_su_valor():
    # PERFIL_NEGOCIO puede ser la clave de un cliente real (ver clientes/): se
    # reporta su presencia, nunca el valor, igual que el resto de variables.
    reporte = generar_reporte({"PERFIL_NEGOCIO": "un_cliente_cualquiera"})

    assert "PERFIL_NEGOCIO: con valor" in reporte
    assert "un_cliente_cualquiera" not in reporte


def test_numero_dueno_con_formato_valido_no_lleva_advertencia():
    reporte = generar_reporte({"NUMERO_DUENO": "573001112233"})

    assert "NUMERO_DUENO: con valor" in reporte
    assert "no parece válido" not in reporte


def test_numero_dueno_con_formato_invalido_avisa_sin_mostrar_el_valor():
    reporte = generar_reporte({"NUMERO_DUENO": "123"})

    assert "NUMERO_DUENO: con valor (formato no parece válido" in reporte
    assert "123" not in reporte.split("NUMERO_DUENO:")[1].split("\n")[0]


def test_variables_del_reporte_semanal_estan_y_se_marcan_como_opcionales():
    reporte = generar_reporte({"REPORTE_SEMANAL_DIA": "lunes"})

    assert "REPORTE_SEMANAL_DIA: con valor" in reporte
    assert "lunes" not in reporte
    for nombre in ("REPORTE_SEMANAL_HORA", "PLANTILLA_REPORTE_SEMANAL_NOMBRE", "PLANTILLA_REPORTE_SEMANAL_IDIOMA"):
        assert f"{nombre}: VACÍO (opcional)" in reporte
    # Las de siempre no cambian: vacías, sin la marca de opcional.
    assert "WHATSAPP_TOKEN: VACÍO\n" in reporte + "\n"


def test_numero_dueno_con_mas_espacios_y_guiones_se_normaliza_antes_de_validar():
    reporte = generar_reporte({"NUMERO_DUENO": "+57 300 111 2233"})

    assert "NUMERO_DUENO: con valor" in reporte
    assert "no parece válido" not in reporte
