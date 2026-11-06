from pago_pedido import confirmar_pago, rechazar_pago
from pedidos import Pedidos


class EnviosTexto:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, texto):
        self.llamadas.append((numero, texto))
        return True


def _pedido_en_verificacion(tmp_path, numero="573001112233"):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.marcar_pago_pendiente(pedido_id, total=16000, ahora=1001.0)
    pedidos.marcar_pago_por_verificar(pedido_id, ahora=1002.0)
    return pedidos, pedido_id


def test_confirmar_pago_marca_pagado_y_notifica_al_cliente(tmp_path):
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)
    texto = EnviosTexto()

    resultado = confirmar_pago(pedidos, pedido_id, ahora=1003.0, enviar_texto_fn=texto)

    assert pedidos.obtener(pedido_id)["estado"] == "pagado"
    assert texto.llamadas[-1][0] == "573001112233"
    assert f"#{pedido_id}" in texto.llamadas[-1][1]
    assert f"#{pedido_id}" in resultado


def test_confirmar_pago_sobre_pedido_inexistente_no_hace_nada(tmp_path):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    texto = EnviosTexto()

    resultado = confirmar_pago(pedidos, 999, ahora=1000.0, enviar_texto_fn=texto)

    assert "No existe" in resultado
    assert texto.llamadas == []


def test_confirmar_pago_sobre_pedido_en_otro_estado_no_hace_nada(tmp_path):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    pedido_id = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    texto = EnviosTexto()

    resultado = confirmar_pago(pedidos, pedido_id, ahora=1001.0, enviar_texto_fn=texto)

    assert "no está esperando verificación" in resultado
    assert texto.llamadas == []
    assert pedidos.obtener(pedido_id)["estado"] == "en_construccion"


def test_doble_pulsacion_de_pago_recibido_no_repite_el_aviso_al_cliente(tmp_path):
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)
    texto = EnviosTexto()

    confirmar_pago(pedidos, pedido_id, ahora=1003.0, enviar_texto_fn=texto)
    cantidad_tras_primera = len(texto.llamadas)
    resultado_segunda = confirmar_pago(pedidos, pedido_id, ahora=1004.0, enviar_texto_fn=texto)

    assert len(texto.llamadas) == cantidad_tras_primera  # no se envía un segundo aviso
    assert "no está esperando verificación" in resultado_segunda


def test_rechazar_pago_vuelve_a_pago_pendiente_y_notifica_al_cliente(tmp_path):
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)
    texto = EnviosTexto()

    resultado = rechazar_pago(pedidos, pedido_id, ahora=1003.0, enviar_texto_fn=texto)

    assert pedidos.obtener(pedido_id)["estado"] == "pago_pendiente"
    assert "no vemos su pago" in texto.llamadas[-1][1].lower()
    assert f"#{pedido_id}" in resultado


def test_rechazar_pago_sobre_pedido_inexistente_no_hace_nada(tmp_path):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    texto = EnviosTexto()

    resultado = rechazar_pago(pedidos, 999, ahora=1000.0, enviar_texto_fn=texto)

    assert "No existe" in resultado
    assert texto.llamadas == []
