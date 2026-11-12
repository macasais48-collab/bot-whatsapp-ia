from pathlib import Path

import gestionar_pedido
from pedidos import Pedidos


def _pedido_en_verificacion(tmp_path, numero="573001112233"):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.marcar_pago_pendiente(pedido_id, total=16000, ahora=1001.0)
    pedidos.marcar_pago_por_verificar(pedido_id, ahora=1002.0)
    return pedidos, pedido_id


def _preparar(monkeypatch, tmp_path, respuestas_input=None, envios=None):
    ruta_bd = tmp_path / "pedidos.db"
    monkeypatch.setenv("RUTA_BD", str(ruta_bd))
    if envios is None:
        envios = []
    monkeypatch.setattr("gestionar_pedido.enviar_texto", lambda numero, texto: envios.append((numero, texto)) or True)
    if respuestas_input is not None:
        respuestas = iter(respuestas_input)
        monkeypatch.setattr("builtins.input", lambda *_: next(respuestas))
    return envios


def test_listar_sin_pedidos_dice_ninguno(tmp_path, monkeypatch, capsys):
    _preparar(monkeypatch, tmp_path)
    Pedidos(tmp_path / "pedidos.db")  # crea el esquema

    gestionar_pedido.main(["listar"])

    salida = capsys.readouterr().out
    assert "pago_pendiente" in salida
    assert "pago_por_verificar" in salida
    assert "(ninguno)" in salida


def test_listar_enmascara_los_telefonos(tmp_path, monkeypatch, capsys):
    _preparar(monkeypatch, tmp_path)
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)

    gestionar_pedido.main(["listar"])

    salida = capsys.readouterr().out
    assert "573001112233" not in salida
    assert "2233" in salida
    assert f"#{pedido_id}" in salida


def test_confirmar_con_si_aplica_el_cambio_y_notifica_al_cliente(tmp_path, monkeypatch, capsys):
    envios = _preparar(monkeypatch, tmp_path, respuestas_input=["si"])
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)

    codigo = gestionar_pedido.main(["confirmar", str(pedido_id)])

    assert codigo == 0
    assert pedidos.obtener(pedido_id)["estado"] == "pagado"
    assert envios[-1][0] == "573001112233"


def test_confirmar_con_no_cancela_sin_aplicar_cambios(tmp_path, monkeypatch, capsys):
    envios = _preparar(monkeypatch, tmp_path, respuestas_input=["no"])
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)

    gestionar_pedido.main(["confirmar", str(pedido_id)])

    assert pedidos.obtener(pedido_id)["estado"] == "pago_por_verificar"
    assert envios == []


def test_no_llego_con_si_vuelve_a_pago_pendiente(tmp_path, monkeypatch, capsys):
    envios = _preparar(monkeypatch, tmp_path, respuestas_input=["si"])
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)

    codigo = gestionar_pedido.main(["no-llego", str(pedido_id)])

    assert codigo == 0
    assert pedidos.obtener(pedido_id)["estado"] == "pago_pendiente"
    assert envios[-1][0] == "573001112233"


def test_confirmar_sobre_id_inexistente_no_hace_nada(tmp_path, monkeypatch, capsys):
    envios = _preparar(monkeypatch, tmp_path)
    Pedidos(tmp_path / "pedidos.db")

    codigo = gestionar_pedido.main(["confirmar", "999"])

    assert codigo == 1
    assert envios == []


def test_confirmar_sobre_pedido_en_otro_estado_no_hace_nada(tmp_path, monkeypatch, capsys):
    envios = _preparar(monkeypatch, tmp_path, respuestas_input=["si"])
    pedidos = Pedidos(tmp_path / "pedidos.db")
    pedido_id = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    gestionar_pedido.main(["confirmar", str(pedido_id)])

    assert pedidos.obtener(pedido_id)["estado"] == "en_construccion"
    assert envios == []


def test_confirmar_dispara_el_aviso_de_pedido_nuevo_resolviendo_domicilio_del_perfil(
    tmp_path, monkeypatch
):
    envios = _preparar(monkeypatch, tmp_path, respuestas_input=["si"])
    monkeypatch.setenv("NUMERO_DUENO", "573005554433")
    monkeypatch.setenv("PLANTILLA_AVISO_PEDIDO_NUEVO_NOMBRE", "aviso_pedido_nuevo")
    monkeypatch.setenv("PLANTILLA_AVISO_PEDIDO_NUEVO_IDIOMA", "es")
    llamadas_plantilla = []
    monkeypatch.setattr(
        "gestionar_pedido.enviar_plantilla",
        lambda numero, nombre, idioma, parametros, botones=None: (
            llamadas_plantilla.append((numero, nombre, idioma, parametros, botones)) or (True, "wamid-prueba")
        ),
    )
    pedidos = Pedidos(tmp_path / "pedidos.db")
    numero_cliente = "573001112233"
    pedido_id = pedidos.crear_en_construccion(numero_cliente, "tamales", ahora=1000.0)
    pedidos.agregar_item(pedido_id, "tamal_sencillo", "Tamal sencillo", 8000, 2, ahora=1000.0)
    pedidos.fijar_entrega(
        pedido_id, "domicilio", ahora=1000.0, paso_siguiente="confirmacion",
        zona_domicilio="centro", direccion_texto="Calle de prueba 1-23",
    )
    pedidos.marcar_pago_pendiente(pedido_id, total=19000, ahora=1001.0)
    pedidos.marcar_pago_por_verificar(pedido_id, ahora=1002.0)

    codigo = gestionar_pedido.main(["confirmar", str(pedido_id)])

    assert codigo == 0
    assert pedidos.obtener(pedido_id)["estado"] == "pagado"
    assert len(llamadas_plantilla) == 1
    numero, nombre, idioma, parametros, botones = llamadas_plantilla[0]
    assert numero == "573005554433"
    assert nombre == "aviso_pedido_nuevo"
    assert idioma == "es"
    assert parametros[0] == str(pedido_id)
    assert "Centro" in parametros[3]  # domicilio resuelto desde el perfil del pedido ("tamales")
    assert "Calle de prueba 1-23" in parametros[3]
    assert parametros[5] == numero_cliente  # teléfono completo del cliente en el contenido
    assert botones is None


# -- Sub-fase 5b: estado listar / estado avanzar --


def _preparar_estado(monkeypatch, tmp_path, respuestas_input=None):
    envios = _preparar(monkeypatch, tmp_path, respuestas_input=respuestas_input)
    envios_con_wamid = []
    monkeypatch.setattr(
        "gestionar_pedido.enviar_texto_con_wamid",
        lambda numero, texto: envios_con_wamid.append((numero, texto)) or (True, "wamid-estado"),
    )
    return envios, envios_con_wamid


def _pedido_confirmado(tmp_path, tipo_entrega="domicilio", numero="573001112233"):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.agregar_item(pedido_id, "producto_a", "Producto A", 5000, 2, ahora=1000.0)
    if tipo_entrega == "domicilio":
        pedidos.fijar_entrega(
            pedido_id, "domicilio", ahora=1000.0, paso_siguiente="confirmacion", zona_domicilio="centro"
        )
    else:
        pedidos.fijar_entrega(pedido_id, "recoger", ahora=1000.0, paso_siguiente="confirmacion")
    pedidos.confirmar_efectivo(pedido_id, total=10000, ahora=1000.0)
    return pedidos, pedido_id


def test_estado_listar_sin_pedidos_activos_dice_ninguno(tmp_path, monkeypatch, capsys):
    _preparar_estado(monkeypatch, tmp_path)
    Pedidos(tmp_path / "pedidos.db")

    codigo = gestionar_pedido.main(["estado", "listar"])

    assert codigo == 0
    assert "(ninguno)" in capsys.readouterr().out


def test_estado_listar_muestra_estado_y_enmascara_el_telefono(tmp_path, monkeypatch, capsys):
    _preparar_estado(monkeypatch, tmp_path)
    _, pedido_id = _pedido_confirmado(tmp_path)

    gestionar_pedido.main(["estado", "listar"])

    salida = capsys.readouterr().out
    assert f"#{pedido_id}" in salida
    assert "En preparación" in salida
    assert "domicilio" in salida
    assert "573001112233" not in salida


def test_estado_avanzar_con_si_aplica_el_siguiente_paso_y_avisa_al_cliente(tmp_path, monkeypatch, capsys):
    _, envios_con_wamid = _preparar_estado(monkeypatch, tmp_path, respuestas_input=["si"])
    pedidos, pedido_id = _pedido_confirmado(tmp_path, tipo_entrega="recoger")

    codigo = gestionar_pedido.main(["estado", "avanzar", str(pedido_id)])

    assert codigo == 0
    assert pedidos.obtener(pedido_id)["estado_entrega"] == "listo_para_recoger"
    assert envios_con_wamid == [("573001112233", f"Su pedido #{pedido_id} está listo para recoger.")]
    assert pedidos.info_aviso_dueno_por_wamid("wamid-estado")["tipo"] == "estado_cliente"
    assert "573001112233" not in capsys.readouterr().out


def test_estado_avanzar_con_no_no_cambia_nada(tmp_path, monkeypatch):
    _, envios_con_wamid = _preparar_estado(monkeypatch, tmp_path, respuestas_input=["no"])
    pedidos, pedido_id = _pedido_confirmado(tmp_path)

    codigo = gestionar_pedido.main(["estado", "avanzar", str(pedido_id)])

    assert codigo == 0
    assert pedidos.obtener(pedido_id)["estado_entrega"] == "en_preparacion"
    assert envios_con_wamid == []


def test_estado_avanzar_sobre_pedido_sin_confirmar_o_inexistente_no_hace_nada(tmp_path, monkeypatch):
    _, envios_con_wamid = _preparar_estado(monkeypatch, tmp_path, respuestas_input=["si"])
    pedidos, en_verificacion = _pedido_en_verificacion(tmp_path)

    assert gestionar_pedido.main(["estado", "avanzar", str(en_verificacion)]) == 1
    assert gestionar_pedido.main(["estado", "avanzar", "999"]) == 1
    assert gestionar_pedido.main(["estado", "avanzar", "abc"]) == 1
    assert envios_con_wamid == []


def test_estado_con_argumentos_invalidos_muestra_el_uso(tmp_path, monkeypatch, capsys):
    _preparar_estado(monkeypatch, tmp_path)
    Pedidos(tmp_path / "pedidos.db")

    codigo = gestionar_pedido.main(["estado"])

    assert codigo == 1
    assert "estado avanzar <id>" in capsys.readouterr().out


def test_gestionar_pedido_nunca_importa_webhook():
    ruta = Path(gestionar_pedido.__file__)
    contenido = ruta.read_text(encoding="utf-8")

    assert "import webhook" not in contenido
    assert "webhook" not in gestionar_pedido.__dict__
