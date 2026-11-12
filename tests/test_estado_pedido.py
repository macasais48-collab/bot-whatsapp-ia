import logging

import pytest

import estado_pedido
from pedidos import (
    ENTREGA_EN_CAMINO,
    ENTREGA_EN_PREPARACION,
    ENTREGA_ENTREGADO,
    ENTREGA_LISTO_PARA_RECOGER,
    Pedidos,
)

NUMERO_CLIENTE = "573001112233"
DOMICILIO = {"centro": {"nombre": "Centro", "costo": 3000, "tiempo_estimado": "30 minutos"}}


class EnviosConWamidFalsos:
    def __init__(self, ok=True, wamid="wamid.estado-1"):
        self.ok = ok
        self.wamid = wamid
        self.llamadas = []

    def __call__(self, numero, texto):
        self.llamadas.append((numero, texto))
        return self.ok, (self.wamid if self.ok else None)


def _pedido_confirmado(pedidos, tipo_entrega="recoger", numero=NUMERO_CLIENTE):
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.agregar_item(pedido_id, "producto_a", "Producto A", 5000, 2, ahora=1000.0)
    if tipo_entrega == "domicilio":
        pedidos.fijar_entrega(
            pedido_id, "domicilio", ahora=1000.0, paso_siguiente="confirmacion", zona_domicilio="centro"
        )
    else:
        pedidos.fijar_entrega(pedido_id, "recoger", ahora=1000.0, paso_siguiente="confirmacion")
    pedidos.confirmar_efectivo(pedido_id, total=10000, ahora=1000.0)
    return pedido_id


@pytest.fixture
def pedidos(tmp_path):
    return Pedidos(tmp_path / "pedidos.db")


# -- Transiciones --


@pytest.mark.parametrize(
    "tipo_entrega, secuencia",
    [
        ("domicilio", [ENTREGA_EN_CAMINO, ENTREGA_ENTREGADO]),
        ("recoger", [ENTREGA_LISTO_PARA_RECOGER, ENTREGA_ENTREGADO]),
    ],
)
def test_secuencia_completa_de_estados_avisa_al_cliente_en_cada_paso(pedidos, tipo_entrega, secuencia):
    pedido_id = _pedido_confirmado(pedidos, tipo_entrega)
    envios = EnviosConWamidFalsos()

    for estado_nuevo in secuencia:
        resultado = estado_pedido.avanzar_estado(pedidos, pedido_id, estado_nuevo, 2000.0, envios)
        assert "Se avisó al cliente" in resultado
        assert pedidos.obtener(pedido_id)["estado_entrega"] == estado_nuevo

    assert [numero for numero, _ in envios.llamadas] == [NUMERO_CLIENTE, NUMERO_CLIENTE]
    assert envios.llamadas[-1][1] == f"Su pedido #{pedido_id} fue entregado. ¡Gracias por su compra!"
    assert estado_pedido.siguiente_estado(pedidos.obtener(pedido_id)) is None


def test_mensajes_al_cliente_de_cada_estado(pedidos):
    domicilio_id = _pedido_confirmado(pedidos, "domicilio")
    recoger_id = _pedido_confirmado(pedidos, "recoger", numero="573009998877")
    envios = EnviosConWamidFalsos()

    estado_pedido.avanzar_estado(pedidos, domicilio_id, ENTREGA_EN_CAMINO, 2000.0, envios)
    estado_pedido.avanzar_estado(pedidos, recoger_id, ENTREGA_LISTO_PARA_RECOGER, 2000.0, envios)

    assert envios.llamadas == [
        (NUMERO_CLIENTE, f"Su pedido #{domicilio_id} va en camino."),
        ("573009998877", f"Su pedido #{recoger_id} está listo para recoger."),
    ]


def test_transicion_que_no_corresponde_al_tipo_de_entrega_no_cambia_nada(pedidos):
    pedido_id = _pedido_confirmado(pedidos, "recoger")
    envios = EnviosConWamidFalsos()

    resultado = estado_pedido.avanzar_estado(pedidos, pedido_id, ENTREGA_EN_CAMINO, 2000.0, envios)

    assert "No se hizo ningún cambio" in resultado
    assert pedidos.obtener(pedido_id)["estado_entrega"] == ENTREGA_EN_PREPARACION
    assert envios.llamadas == []


def test_saltarse_un_paso_no_esta_permitido(pedidos):
    pedido_id = _pedido_confirmado(pedidos, "domicilio")
    envios = EnviosConWamidFalsos()

    resultado = estado_pedido.avanzar_estado(pedidos, pedido_id, ENTREGA_ENTREGADO, 2000.0, envios)

    assert "No se hizo ningún cambio" in resultado
    assert pedidos.obtener(pedido_id)["estado_entrega"] == ENTREGA_EN_PREPARACION
    assert envios.llamadas == []


def test_doble_pulsacion_no_duplica_el_aviso_al_cliente(pedidos):
    pedido_id = _pedido_confirmado(pedidos, "domicilio")
    envios = EnviosConWamidFalsos()

    estado_pedido.avanzar_estado(pedidos, pedido_id, ENTREGA_EN_CAMINO, 2000.0, envios)
    segundo = estado_pedido.avanzar_estado(pedidos, pedido_id, ENTREGA_EN_CAMINO, 2001.0, envios)

    assert len(envios.llamadas) == 1
    assert "No se hizo ningún cambio" in segundo
    assert pedidos.obtener(pedido_id)["estado_entrega"] == ENTREGA_EN_CAMINO


def test_pedido_inexistente_o_sin_confirmar_no_avanza(pedidos):
    envios = EnviosConWamidFalsos()
    en_pago = pedidos.crear_en_construccion(NUMERO_CLIENTE, "tamales", ahora=1000.0)
    pedidos.marcar_pago_pendiente(en_pago, total=10000, ahora=1000.0)

    assert "No existe" in estado_pedido.avanzar_estado(pedidos, 999, ENTREGA_EN_CAMINO, 2000.0, envios)
    assert "todavía no está confirmado" in estado_pedido.avanzar_estado(
        pedidos, en_pago, ENTREGA_EN_CAMINO, 2000.0, envios
    )
    assert envios.llamadas == []


def test_el_wamid_del_aviso_se_registra_como_estado_cliente(pedidos):
    pedido_id = _pedido_confirmado(pedidos, "domicilio")

    estado_pedido.avanzar_estado(
        pedidos, pedido_id, ENTREGA_EN_CAMINO, 2000.0, EnviosConWamidFalsos(wamid="wamid.aviso-estado")
    )

    assert pedidos.info_aviso_dueno_por_wamid("wamid.aviso-estado") == {
        "pedido_id": pedido_id, "tipo": "estado_cliente",
    }


def test_si_el_aviso_al_cliente_falla_el_estado_queda_aplicado_y_se_registra_como_info(pedidos, caplog):
    pedido_id = _pedido_confirmado(pedidos, "domicilio")
    caplog.set_level(logging.INFO, logger="estado_pedido")

    resultado = estado_pedido.avanzar_estado(
        pedidos, pedido_id, ENTREGA_EN_CAMINO, 2000.0, EnviosConWamidFalsos(ok=False)
    )

    assert pedidos.obtener(pedido_id)["estado_entrega"] == ENTREGA_EN_CAMINO
    assert "No se pudo avisar al cliente" in resultado
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    mensajes = "\n".join(r.getMessage() for r in caplog.records)
    assert NUMERO_CLIENTE not in mensajes  # teléfono siempre enmascarado en el log


# -- Botones y filas --


def test_id_de_boton_ida_y_vuelta():
    id_boton = estado_pedido.id_boton_avanzar(42, ENTREGA_LISTO_PARA_RECOGER)

    assert id_boton == "avanzar_42_listo_para_recoger"
    assert estado_pedido.interpretar_boton_avanzar(id_boton) == (42, ENTREGA_LISTO_PARA_RECOGER)


@pytest.mark.parametrize(
    "id_boton",
    [
        "avanzar_42_en_preparacion",  # no es un destino válido
        "avanzar_42_cualquier_cosa",
        "avanzar_x_en_camino",
        "avanzar__en_camino",
        "pago_recibido_42",
        "avanzar_42",
    ],
)
def test_ids_de_boton_manipulados_se_rechazan(id_boton):
    assert estado_pedido.interpretar_boton_avanzar(id_boton) is None


def test_interpretar_fila():
    assert estado_pedido.interpretar_fila("ver_pedido_7") == ("ver", 7)
    assert estado_pedido.interpretar_fila("pedidos_pagina_2") == ("pagina", 2)
    assert estado_pedido.interpretar_fila("pedidos_pagina_0") is None
    assert estado_pedido.interpretar_fila("ver_pedido_abc") is None
    assert estado_pedido.interpretar_fila("producto_a") is None


def test_detalle_para_dueno_ofrece_un_solo_boton_con_el_siguiente_paso(pedidos):
    domicilio_id = _pedido_confirmado(pedidos, "domicilio")
    recoger_id = _pedido_confirmado(pedidos, "recoger")

    texto, botones = estado_pedido.detalle_para_dueno(pedidos.obtener(domicilio_id), DOMICILIO)
    assert botones == [{"id": f"avanzar_{domicilio_id}_en_camino", "titulo": "Marcar en camino"}]
    assert "2 x Producto A" in texto
    assert "En preparación" in texto

    _, botones = estado_pedido.detalle_para_dueno(pedidos.obtener(recoger_id), DOMICILIO)
    assert botones == [{"id": f"avanzar_{recoger_id}_listo_para_recoger", "titulo": "Listo para recoger"}]


def test_titulos_de_boton_respetan_el_limite_de_meta():
    assert all(len(titulo) <= 20 for titulo in estado_pedido.TITULO_BOTON_AVANZAR.values())


@pytest.mark.parametrize("texto", ["pedidos", "Pedidos", "  PEDIDOS  ", "pédidos"])
def test_palabra_clave_pedidos_sin_distinguir_mayusculas_ni_tildes(texto):
    assert estado_pedido.es_palabra_clave_pedidos(texto)


@pytest.mark.parametrize("texto", ["pedido", "mis pedidos", "", None])
def test_otros_textos_no_son_la_palabra_clave(texto):
    assert not estado_pedido.es_palabra_clave_pedidos(texto)


# -- Lista paginada --


def _crear_activos(pedidos, cantidad):
    return [_pedido_confirmado(pedidos, numero=f"57300000{i:04d}") for i in range(cantidad)]


def test_sin_pedidos_activos_no_hay_lista(pedidos):
    assert estado_pedido.pagina_de_pedidos_activos(pedidos, 1) is None


def test_con_10_o_menos_se_muestran_todos_sin_ver_mas(pedidos):
    ids = _crear_activos(pedidos, 10)

    secciones = estado_pedido.pagina_de_pedidos_activos(pedidos, 1)

    filas = secciones[0]["filas"]
    assert [f["id"] for f in filas] == [f"ver_pedido_{i}" for i in ids]
    assert all(len(f["titulo"]) <= 24 and len(f["descripcion"]) <= 72 for f in filas)


def test_con_mas_de_10_se_muestran_9_y_ver_mas_y_la_pagina_siguiente_trae_el_resto(pedidos):
    ids = _crear_activos(pedidos, 12)

    filas_1 = estado_pedido.pagina_de_pedidos_activos(pedidos, 1)[0]["filas"]
    filas_2 = estado_pedido.pagina_de_pedidos_activos(pedidos, 2)[0]["filas"]

    assert len(filas_1) == 10
    assert [f["id"] for f in filas_1[:9]] == [f"ver_pedido_{i}" for i in ids[:9]]
    assert filas_1[9]["id"] == "pedidos_pagina_2"
    assert filas_1[9]["titulo"] == "Ver más"
    assert [f["id"] for f in filas_2] == [f"ver_pedido_{i}" for i in ids[9:]]


def test_con_20_activos_la_segunda_pagina_tambien_tiene_ver_mas(pedidos):
    ids = _crear_activos(pedidos, 20)

    filas_2 = estado_pedido.pagina_de_pedidos_activos(pedidos, 2)[0]["filas"]
    filas_3 = estado_pedido.pagina_de_pedidos_activos(pedidos, 3)[0]["filas"]

    assert [f["id"] for f in filas_2[:9]] == [f"ver_pedido_{i}" for i in ids[9:18]]
    assert filas_2[9]["id"] == "pedidos_pagina_3"
    assert [f["id"] for f in filas_3] == [f"ver_pedido_{i}" for i in ids[18:]]


def test_la_lista_nunca_incluye_telefono_ni_direccion(pedidos):
    pedido_id = pedidos.crear_en_construccion(NUMERO_CLIENTE, "tamales", ahora=1000.0)
    pedidos.agregar_item(pedido_id, "producto_a", "Producto A", 5000, 1, ahora=1000.0)
    pedidos.fijar_entrega(
        pedido_id, "domicilio", ahora=1000.0, paso_siguiente="confirmacion",
        zona_domicilio="centro", direccion_texto="Calle 10 #5-23",
    )
    pedidos.confirmar_efectivo(pedido_id, total=8000, ahora=1000.0)

    secciones = estado_pedido.pagina_de_pedidos_activos(pedidos, 1)

    contenido = repr(secciones)
    assert NUMERO_CLIENTE not in contenido
    assert "Calle 10" not in contenido
