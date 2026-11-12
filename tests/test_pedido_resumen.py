from pedido_resumen import construir_resumen, entrega_una_linea, formatear_pesos, resumen_productos_una_linea

DOMICILIO = {
    "centro": {"nombre": "Centro", "costo": 3000, "tiempo_estimado": "20-30 minutos"},
}


def _pedido(items=None, tipo_entrega="recoger", zona_domicilio=None, direccion_texto=None, latitud=None):
    return {
        "items": items or [],
        "tipo_entrega": tipo_entrega,
        "zona_domicilio": zona_domicilio,
        "direccion_texto": direccion_texto,
        "latitud": latitud,
    }


def test_formatear_pesos():
    assert formatear_pesos(16000) == "$16.000"


def test_construir_resumen_recoger_en_local():
    pedido = _pedido(items=[{"cantidad": 2, "nombre": "Tamal sencillo", "subtotal": 16000}])

    texto, total = construir_resumen(pedido, DOMICILIO)

    assert "Entrega: Recoger en el local." in texto
    assert total == 16000


def test_construir_resumen_domicilio_suma_el_costo():
    pedido = _pedido(
        items=[{"cantidad": 1, "nombre": "Tamal especial", "subtotal": 12000}],
        tipo_entrega="domicilio", zona_domicilio="centro", direccion_texto="Calle 1 # 2-3",
    )

    texto, total = construir_resumen(pedido, DOMICILIO)

    assert "Domicilio - Centro" in texto
    assert "Calle 1 # 2-3" in texto
    assert total == 15000


def test_resumen_productos_una_linea_varios_productos():
    pedido = _pedido(items=[
        {"cantidad": 2, "nombre": "Producto especial", "subtotal": 31000},
        {"cantidad": 1, "nombre": "Bebida", "subtotal": 15000},
    ])

    assert resumen_productos_una_linea(pedido) == "2 x Producto especial, 1 x Bebida"


def test_resumen_productos_una_linea_recorta_si_supera_el_limite():
    pedido = _pedido(items=[{"cantidad": 1, "nombre": "x" * 50, "subtotal": 1000}])

    resultado = resumen_productos_una_linea(pedido, limite=20)

    assert len(resultado) == 20
    assert resultado.endswith("…")


def test_resumen_productos_una_linea_nunca_tiene_saltos_de_linea_ni_tabulaciones():
    pedido = _pedido(items=[{"cantidad": 1, "nombre": "Producto\ncon\tsaltos", "subtotal": 1000}])

    resultado = resumen_productos_una_linea(pedido)

    assert "\n" not in resultado
    assert "\t" not in resultado


def test_entrega_una_linea_recoger():
    pedido = _pedido()

    assert entrega_una_linea(pedido, DOMICILIO) == "Recoger en el local"


def test_entrega_una_linea_domicilio_con_direccion():
    pedido = _pedido(tipo_entrega="domicilio", zona_domicilio="centro", direccion_texto="Calle 1 # 2-3")

    assert entrega_una_linea(pedido, DOMICILIO) == "Domicilio - Centro, Calle 1 # 2-3"


def test_entrega_una_linea_domicilio_con_ubicacion_compartida():
    pedido = _pedido(tipo_entrega="domicilio", zona_domicilio="centro", latitud=4.6)

    assert entrega_una_linea(pedido, DOMICILIO) == "Domicilio - Centro, ubicación compartida por WhatsApp"


def test_entrega_una_linea_sanea_una_direccion_escrita_en_varias_lineas():
    direccion = "Calle 1 # 2-3\nApto 401\t\tTorre B    cerca al parque"
    pedido = _pedido(tipo_entrega="domicilio", zona_domicilio="centro", direccion_texto=direccion)

    resultado = entrega_una_linea(pedido, DOMICILIO)

    assert "\n" not in resultado
    assert "\t" not in resultado
    assert "    " not in resultado  # nunca 4+ espacios seguidos (regla de Meta)


def test_entrega_una_linea_respeta_el_limite_de_longitud():
    pedido = _pedido(tipo_entrega="domicilio", zona_domicilio="centro", direccion_texto="x" * 300)

    resultado = entrega_una_linea(pedido, DOMICILIO, limite=50)

    assert len(resultado) == 50
