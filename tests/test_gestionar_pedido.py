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
