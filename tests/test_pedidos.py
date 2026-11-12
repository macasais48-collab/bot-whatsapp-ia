import sqlite3

from pedidos import (
    ENTREGA_EN_CAMINO,
    ENTREGA_EN_PREPARACION,
    ENTREGA_ENTREGADO,
    ENTREGA_LISTO_PARA_RECOGER,
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


# -- Sub-fase 5b: estado de entrega --


def _pedido_confirmado(pedidos, numero="573001112233", tipo_entrega="recoger", ahora=1000.0):
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=ahora)
    if tipo_entrega == "domicilio":
        pedidos.fijar_entrega(pedido_id, "domicilio", ahora=ahora, paso_siguiente="confirmacion", zona_domicilio="centro")
    else:
        pedidos.fijar_entrega(pedido_id, "recoger", ahora=ahora, paso_siguiente="confirmacion")
    pedidos.confirmar_efectivo(pedido_id, total=10000, ahora=ahora)
    return pedido_id


def test_una_base_sin_estado_entrega_se_migra_marcando_entregados_solo_los_confirmados(tmp_path):
    ruta_bd = tmp_path / "pedidos_sin_estado_entrega.db"
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
                metodo_pago TEXT,
                creado_en REAL NOT NULL,
                actualizado_en REAL NOT NULL
            )
            """
        )
        for estado in ("recibido", "pagado", "pago_pendiente", "pago_por_verificar", "cancelado", "en_construccion"):
            conexion.execute(
                "INSERT INTO pedidos (numero_cliente, perfil, estado, paso, total, creado_en, actualizado_en) "
                "VALUES ('573001112233', 'tamales', ?, 'producto', 5000, 1000.0, 1000.0)",
                (estado,),
            )
        conexion.commit()

    pedidos = Pedidos(ruta_bd)

    with sqlite3.connect(ruta_bd) as conexion:
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(pedidos)").fetchall()}
    assert "estado_entrega" in columnas
    # Ningún pedido se pierde y su estado de pago no cambia.
    estados = {pedidos.obtener(i)["estado"]: pedidos.obtener(i)["estado_entrega"] for i in range(1, 7)}
    assert estados == {
        "recibido": "entregado",
        "pagado": "entregado",
        "pago_pendiente": None,
        "pago_por_verificar": None,
        "cancelado": None,
        "en_construccion": None,
    }
    assert pedidos.obtener(1)["total"] == 5000
    # Ninguno de los migrados aparece como activo.
    assert pedidos.listar_activos_entrega() == []


def test_la_migracion_de_estado_entrega_no_vuelve_a_correr_al_reabrir_la_base(tmp_path):
    ruta_bd = tmp_path / "pedidos.db"
    pedidos = Pedidos(ruta_bd)
    pedido_id = _pedido_confirmado(pedidos)

    Pedidos(ruta_bd)  # reabrir: la columna ya existe, no se marca nada como entregado

    assert Pedidos(ruta_bd).obtener(pedido_id)["estado_entrega"] == ENTREGA_EN_PREPARACION


def test_confirmar_efectivo_deja_el_pedido_en_preparacion(tmp_path):
    pedidos = _crear_pedidos(tmp_path)

    pedido_id = _pedido_confirmado(pedidos)

    assert pedidos.obtener(pedido_id)["estado_entrega"] == ENTREGA_EN_PREPARACION


def test_marcar_pagado_deja_el_pedido_en_preparacion_y_antes_no_tiene_estado_de_entrega(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    pedido_id = pedidos.crear_en_construccion("573001112233", "tamales", ahora=1000.0)
    pedidos.marcar_pago_pendiente(pedido_id, total=10000, ahora=1001.0)
    pedidos.marcar_pago_por_verificar(pedido_id, ahora=1002.0)
    assert pedidos.obtener(pedido_id)["estado_entrega"] is None

    pedidos.marcar_pagado(pedido_id, ahora=1003.0)

    assert pedidos.obtener(pedido_id)["estado_entrega"] == ENTREGA_EN_PREPARACION


def test_avanzar_estado_entrega_solo_cambia_si_sigue_en_el_estado_esperado(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    pedido_id = _pedido_confirmado(pedidos, tipo_entrega="domicilio")

    primero = pedidos.avanzar_estado_entrega(pedido_id, ENTREGA_EN_PREPARACION, ENTREGA_EN_CAMINO, ahora=2000.0)
    segundo = pedidos.avanzar_estado_entrega(pedido_id, ENTREGA_EN_PREPARACION, ENTREGA_EN_CAMINO, ahora=2001.0)

    assert primero is True
    assert segundo is False
    pedido = pedidos.obtener(pedido_id)
    assert pedido["estado_entrega"] == ENTREGA_EN_CAMINO
    assert pedido["actualizado_en"] == 2000.0


def test_listar_activos_entrega_ordena_del_mas_antiguo_y_excluye_entregados_y_en_pago(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    primero = _pedido_confirmado(pedidos, numero="573000000001")
    segundo = _pedido_confirmado(pedidos, numero="573000000002", tipo_entrega="domicilio")
    entregado = _pedido_confirmado(pedidos, numero="573000000003")
    pedidos.avanzar_estado_entrega(entregado, ENTREGA_EN_PREPARACION, ENTREGA_LISTO_PARA_RECOGER, ahora=2000.0)
    pedidos.avanzar_estado_entrega(entregado, ENTREGA_LISTO_PARA_RECOGER, ENTREGA_ENTREGADO, ahora=2001.0)
    en_pago = pedidos.crear_en_construccion("573000000004", "tamales", ahora=1000.0)
    pedidos.marcar_pago_pendiente(en_pago, total=10000, ahora=1001.0)
    pedidos.crear_en_construccion("573000000005", "tamales", ahora=1000.0)

    activos = pedidos.listar_activos_entrega()

    assert [p["id"] for p in activos] == [primero, segundo]


def test_listar_activos_entrega_con_limite_y_desplazamiento(tmp_path):
    pedidos = _crear_pedidos(tmp_path)
    ids = [_pedido_confirmado(pedidos, numero=f"57300000{i:04d}") for i in range(5)]

    assert [p["id"] for p in pedidos.listar_activos_entrega(0, 2)] == ids[:2]
    assert [p["id"] for p in pedidos.listar_activos_entrega(2, 2)] == ids[2:4]
    assert [p["id"] for p in pedidos.listar_activos_entrega(4, 2)] == ids[4:]
