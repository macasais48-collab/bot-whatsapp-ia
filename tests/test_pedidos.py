from pedidos import ESTADO_CANCELADO, ESTADO_EN_CONSTRUCCION, ESTADO_RECIBIDO, Pedidos


def _crear_pedidos(tmp_path, nombre="pedidos.db"):
    return Pedidos(tmp_path / nombre)


def test_no_hay_pedido_en_construccion_para_un_numero_nuevo(tmp_path):
    pedidos = _crear_pedidos(tmp_path)

    assert pedidos.obtener_en_construccion("573001112233") is None


def test_crear_en_construccion_queda_disponible_con_el_paso_inicial(tmp_path):
    pedidos = _crear_pedidos(tmp_path)

    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    pedido = pedidos.obtener_en_construccion("573001112233")

    assert pedido["id"] == id_pedido
    assert pedido["estado"] == ESTADO_EN_CONSTRUCCION
    assert pedido["paso"] == "producto"
    assert pedido["items"] == []
    assert pedido["consentimiento_aceptado"] is None
    assert pedido["actualizado_en"] == 1000.0


def test_agregar_item_calcula_el_subtotal_y_pasa_al_paso_agregar_otro_o_continuar(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    pedidos.fijar_producto_pendiente(id_pedido, "tamal_sencillo", ahora=1001.0)
    pedidos.agregar_item(id_pedido, "tamal_sencillo", "Tamal sencillo", 8000, 3, ahora=1002.0)

    pedido = pedidos.obtener_en_construccion("573001112233")
    assert pedido["paso"] == "agregar_otro_o_continuar"
    assert pedido["producto_pendiente"] is None
    assert pedido["items"] == [
        {"clave_producto": "tamal_sencillo", "nombre": "Tamal sencillo", "precio_unitario": 8000, "cantidad": 3, "subtotal": 24000}
    ]


def test_vaciar_items_borra_items_y_resetea_entrega(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    pedidos.agregar_item(id_pedido, "tamal_sencillo", "Tamal sencillo", 8000, 2, ahora=1001.0)
    pedidos.fijar_entrega(id_pedido, "domicilio", ahora=1002.0, paso_siguiente="confirmacion", zona_domicilio="centro")

    pedidos.vaciar_items(id_pedido, ahora=1003.0)

    pedido = pedidos.obtener_en_construccion("573001112233")
    assert pedido["items"] == []
    assert pedido["tipo_entrega"] is None
    assert pedido["zona_domicilio"] is None
    assert pedido["paso"] == "producto"


def test_confirmar_cambia_estado_y_ya_no_aparece_como_en_construccion(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    pedidos.confirmar(id_pedido, total=24000, ahora=1005.0)

    assert pedidos.obtener_en_construccion("573001112233") is None


def test_cancelar_cambia_estado_y_ya_no_aparece_como_en_construccion(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    pedidos.cancelar(id_pedido, ahora=1005.0)

    assert pedidos.obtener_en_construccion("573001112233") is None


def test_un_solo_pedido_en_construccion_por_numero(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    primero = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    pedidos.confirmar(primero, total=1000, ahora=1001.0)

    segundo = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1002.0)

    pedido = pedidos.obtener_en_construccion("573001112233")
    assert pedido["id"] == segundo
    assert pedido["id"] != primero


def test_dos_numeros_con_pedidos_simultaneos_no_se_mezclan(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_a = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    id_b = pedidos.crear_en_construccion("573009998877", "tamales", ahora=1000.0)

    pedidos.agregar_item(id_a, "tamal_sencillo", "Tamal sencillo", 8000, 1, ahora=1001.0)
    pedidos.fijar_producto_pendiente(id_b, "bebida", ahora=1001.0)

    pedido_a = pedidos.obtener_en_construccion("573001112233")
    pedido_b = pedidos.obtener_en_construccion("573009998877")

    assert pedido_a["id"] == id_a
    assert pedido_a["items"][0]["clave_producto"] == "tamal_sencillo"
    assert pedido_b["id"] == id_b
    assert pedido_b["items"] == []
    assert pedido_b["producto_pendiente"] == "bebida"


def test_tocar_actualiza_actualizado_en_sin_cambiar_nada_mas(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    pedidos.tocar(id_pedido, ahora=2000.0)

    pedido = pedidos.obtener_en_construccion("573001112233")
    assert pedido["actualizado_en"] == 2000.0
    assert pedido["paso"] == "producto"
