import sqlite3

from pedidos import (
    ESTADO_CANCELADO,
    ESTADO_EN_CONSTRUCCION,
    ESTADO_PAGADO,
    ESTADO_PAGO_PENDIENTE,
    ESTADO_PAGO_POR_VERIFICAR,
    ESTADO_RECIBIDO,
    Pedidos,
)


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


def test_confirmar_efectivo_deja_el_pedido_recibido_con_metodo_pago_efectivo(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    pedidos.confirmar_efectivo(id_pedido, total=16000, ahora=1005.0)

    pedido = pedidos.obtener(id_pedido)
    assert pedido["estado"] == ESTADO_RECIBIDO
    assert pedido["metodo_pago"] == "efectivo"
    assert pedido["total"] == 16000
    assert pedidos.obtener_activo("573001112233") is None


def test_marcar_pago_pendiente_fija_total_metodo_y_paso(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    pedidos.marcar_pago_pendiente(id_pedido, total=16000, ahora=1005.0)

    pedido = pedidos.obtener(id_pedido)
    assert pedido["estado"] == ESTADO_PAGO_PENDIENTE
    assert pedido["metodo_pago"] == "qr"
    assert pedido["total"] == 16000
    assert pedido["paso"] == "pago_pendiente"


def test_marcar_pago_por_verificar_y_marcar_pagado(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    pedidos.marcar_pago_pendiente(id_pedido, total=16000, ahora=1001.0)

    pedidos.marcar_pago_por_verificar(id_pedido, ahora=1002.0)
    assert pedidos.obtener(id_pedido)["estado"] == ESTADO_PAGO_POR_VERIFICAR

    pedidos.marcar_pagado(id_pedido, ahora=1003.0)
    pedido = pedidos.obtener(id_pedido)
    assert pedido["estado"] == ESTADO_PAGADO
    assert pedidos.obtener_activo("573001112233") is None


def test_volver_a_pago_pendiente_regresa_desde_pago_por_verificar(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    pedidos.marcar_pago_pendiente(id_pedido, total=16000, ahora=1001.0)
    pedidos.marcar_pago_por_verificar(id_pedido, ahora=1002.0)

    pedidos.volver_a_pago_pendiente(id_pedido, ahora=1003.0)

    pedido = pedidos.obtener(id_pedido)
    assert pedido["estado"] == ESTADO_PAGO_PENDIENTE
    assert pedido["paso"] == "pago_pendiente"


def test_obtener_activo_incluye_en_construccion_pago_pendiente_y_pago_por_verificar(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_pedido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    assert pedidos.obtener_activo("573001112233")["id"] == id_pedido

    pedidos.marcar_pago_pendiente(id_pedido, total=16000, ahora=1001.0)
    assert pedidos.obtener_activo("573001112233")["id"] == id_pedido

    pedidos.marcar_pago_por_verificar(id_pedido, ahora=1002.0)
    assert pedidos.obtener_activo("573001112233")["id"] == id_pedido


def test_obtener_activo_no_incluye_recibido_pagado_ni_cancelado(tmp_path):
    pedidos = _crear_pedidos(tmp_path)

    id_recibido = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    pedidos.confirmar(id_recibido, total=1000, ahora=1001.0)
    assert pedidos.obtener_activo("573001112233") is None

    id_pagado = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1002.0)
    pedidos.marcar_pago_pendiente(id_pagado, total=1000, ahora=1003.0)
    pedidos.marcar_pago_por_verificar(id_pagado, ahora=1004.0)
    pedidos.marcar_pagado(id_pagado, ahora=1005.0)
    assert pedidos.obtener_activo("573001112233") is None

    id_cancelado = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1006.0)
    pedidos.cancelar(id_cancelado, ahora=1007.0)
    assert pedidos.obtener_activo("573001112233") is None


def test_obtener_por_id_devuelve_none_si_no_existe(tmp_path):
    pedidos = _crear_pedidos(tmp_path)

    assert pedidos.obtener(999) is None


def test_listar_por_estados_filtra_y_ordena_por_id(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    id_a = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    id_b = pedidos.crear_en_construccion("573009998877", "tamales", ahora=1001.0)
    pedidos.marcar_pago_pendiente(id_a, total=8000, ahora=1002.0)
    pedidos.marcar_pago_pendiente(id_b, total=12000, ahora=1003.0)
    pedidos.marcar_pago_por_verificar(id_b, ahora=1004.0)

    pendientes = pedidos.listar_por_estados([ESTADO_PAGO_PENDIENTE])
    assert [pedido["id"] for pedido in pendientes] == [id_a]

    en_verificacion = pedidos.listar_por_estados([ESTADO_PAGO_POR_VERIFICAR])
    assert [pedido["id"] for pedido in en_verificacion] == [id_b]

    ambos = pedidos.listar_por_estados([ESTADO_PAGO_PENDIENTE, ESTADO_PAGO_POR_VERIFICAR])
    assert {pedido["id"] for pedido in ambos} == {id_a, id_b}


def test_una_base_del_esquema_anterior_sin_metodo_pago_se_migra_sin_perder_datos(tmp_path):
    ruta_bd = tmp_path / "pedidos_viejos.db"
    with sqlite3.connect(ruta_bd) as conexion:
        conexion.execute(
            """
            CREATE TABLE pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_cliente TEXT NOT NULL,
                perfil TEXT NOT NULL,
                estado TEXT NOT NULL,
                paso TEXT NOT NULL,
                producto_pendiente TEXT,
                consentimiento_aceptado INTEGER,
                tipo_entrega TEXT,
                zona_domicilio TEXT,
                direccion_texto TEXT,
                latitud REAL,
                longitud REAL,
                total INTEGER,
                creado_en REAL NOT NULL,
                actualizado_en REAL NOT NULL
            )
            """
        )
        conexion.execute(
            "INSERT INTO pedidos (numero_cliente, perfil, estado, paso, creado_en, actualizado_en) "
            "VALUES ('573001112233', 'tamales', 'recibido', 'producto', 1000.0, 1000.0)"
        )
        conexion.commit()

    pedidos = Pedidos(ruta_bd)

    with sqlite3.connect(ruta_bd) as conexion:
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(pedidos)").fetchall()}
    assert "metodo_pago" in columnas

    pedido = pedidos.obtener(1)
    assert pedido["numero_cliente"] == "573001112233"
    assert pedido["estado"] == "recibido"
    assert pedido["metodo_pago"] is None


def test_registrar_y_consultar_wamid_de_aviso_al_dueno(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    pedido_id = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)

    pedidos.registrar_wamid_aviso_dueno("wamid-plantilla-1", pedido_id, "plantilla", ahora=1001.0)
    pedidos.registrar_wamid_aviso_dueno("wamid-comprobante-1", pedido_id, "comprobante", ahora=1002.0)

    assert pedidos.info_aviso_dueno_por_wamid("wamid-plantilla-1") == {
        "pedido_id": pedido_id, "tipo": "plantilla",
    }
    assert pedidos.info_aviso_dueno_por_wamid("wamid-comprobante-1") == {
        "pedido_id": pedido_id, "tipo": "comprobante",
    }


def test_info_aviso_dueno_por_wamid_desconocido_devuelve_none(tmp_path):
    pedidos = _crear_pedidos(tmp_path)

    assert pedidos.info_aviso_dueno_por_wamid("wamid-que-no-existe") is None
