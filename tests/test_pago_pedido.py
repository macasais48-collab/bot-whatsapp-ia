from pago_pedido import avisar_pedido_nuevo, confirmar_pago, rechazar_pago
from pedidos import Pedidos


class EnviosTexto:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, texto):
        self.llamadas.append((numero, texto))
        return True


class EnviosPlantilla:
    def __init__(self, ok=True, wamid="wamid-pedido-nuevo-1"):
        self.llamadas = []
        self._ok = ok
        self._wamid = wamid

    def __call__(self, numero, nombre_plantilla, idioma, parametros_cuerpo, botones=None):
        self.llamadas.append((numero, nombre_plantilla, idioma, parametros_cuerpo, botones))
        return self._ok, (self._wamid if self._ok else None)


def _pedido_confirmado_efectivo(tmp_path, numero="573001112233"):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.agregar_item(pedido_id, "tamal_sencillo", "Tamal sencillo", 8000, 2, ahora=1000.0)
    pedidos.fijar_entrega(pedido_id, "recoger", ahora=1000.0, paso_siguiente="confirmacion")
    pedidos.confirmar_efectivo(pedido_id, total=16000, ahora=1001.0)
    return pedidos, pedidos.obtener(pedido_id)


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


def test_avisar_pedido_nuevo_sin_numero_dueno_no_hace_nada(tmp_path):
    pedidos, pedido = _pedido_confirmado_efectivo(tmp_path)
    texto = EnviosTexto()

    avisar_pedido_nuevo(pedidos, None, pedido, {}, 1002.0, texto)

    assert texto.llamadas == []


def test_avisar_pedido_nuevo_por_plantilla_incluye_el_telefono_completo_y_registra_el_wamid(tmp_path):
    pedidos, pedido = _pedido_confirmado_efectivo(tmp_path)
    texto = EnviosTexto()
    plantilla = EnviosPlantilla()

    avisar_pedido_nuevo(
        pedidos, "573005554433", pedido, {}, 1002.0, texto,
        enviar_plantilla_fn=plantilla, plantilla_nombre="aviso_pedido_nuevo", plantilla_idioma="es",
    )

    assert texto.llamadas == []  # va por plantilla, no por el texto libre
    numero, nombre, idioma, parametros, botones = plantilla.llamadas[0]
    assert numero == "573005554433"
    assert nombre == "aviso_pedido_nuevo"
    assert idioma == "es"
    assert botones is None  # es informativa, sin botones
    assert parametros[0] == str(pedido["id"])
    assert "2 x Tamal sencillo" in parametros[1]
    assert parametros[2] == "$16.000"
    assert parametros[3] == "Recoger en el local"
    assert parametros[4] == "Efectivo"
    assert parametros[5] == "573001112233"  # teléfono COMPLETO en el contenido (excepción deliberada)
    assert pedidos.info_aviso_dueno_por_wamid("wamid-pedido-nuevo-1") == {
        "pedido_id": pedido["id"], "tipo": "pedido_nuevo",
    }


def test_avisar_pedido_nuevo_sin_plantilla_configurada_usa_texto_libre(tmp_path):
    pedidos, pedido = _pedido_confirmado_efectivo(tmp_path)
    texto = EnviosTexto()

    avisar_pedido_nuevo(pedidos, "573005554433", pedido, {}, 1002.0, texto)

    assert texto.llamadas[-1][0] == "573005554433"
    assert "573001112233" in texto.llamadas[-1][1]


def test_avisar_pedido_nuevo_registra_en_el_log_con_el_telefono_enmascarado(tmp_path, caplog):
    import logging

    pedidos, pedido = _pedido_confirmado_efectivo(tmp_path)
    texto = EnviosTexto()
    caplog.set_level(logging.INFO, logger="pago_pedido")

    avisar_pedido_nuevo(pedidos, "573005554433", pedido, {}, 1002.0, texto)

    mensajes = "\n".join(r.getMessage() for r in caplog.records)
    assert "573001112233" not in mensajes
    assert "2233" in mensajes


def test_confirmar_pago_tambien_dispara_el_aviso_de_pedido_nuevo(tmp_path):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    numero = "573001112233"
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.agregar_item(pedido_id, "tamal_sencillo", "Tamal sencillo", 8000, 2, ahora=1000.0)
    pedidos.fijar_entrega(pedido_id, "recoger", ahora=1000.0, paso_siguiente="confirmacion")
    pedidos.marcar_pago_pendiente(pedido_id, total=16000, ahora=1001.0)
    pedidos.marcar_pago_por_verificar(pedido_id, ahora=1002.0)
    texto = EnviosTexto()
    plantilla = EnviosPlantilla()

    confirmar_pago(
        pedidos, pedido_id, ahora=1003.0, enviar_texto_fn=texto,
        domicilio={}, numero_dueno="573005554433",
        enviar_plantilla_fn=plantilla, plantilla_nombre="aviso_pedido_nuevo", plantilla_idioma="es",
    )

    assert pedidos.obtener(pedido_id)["estado"] == "pagado"
    assert texto.llamadas[-1][0] == numero  # el cliente sigue recibiendo su confirmación de siempre
    assert plantilla.llamadas and plantilla.llamadas[0][0] == "573005554433"


def test_confirmar_pago_sin_numero_dueno_no_dispara_ningun_aviso_de_pedido_nuevo(tmp_path):
    pedidos, pedido_id = _pedido_en_verificacion(tmp_path)
    texto = EnviosTexto()
    plantilla = EnviosPlantilla()

    confirmar_pago(pedidos, pedido_id, ahora=1003.0, enviar_texto_fn=texto, enviar_plantilla_fn=plantilla)

    assert plantilla.llamadas == []
