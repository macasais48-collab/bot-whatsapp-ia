import threading

from citas import (
    ESTADO_CANCELADA,
    ESTADO_CONFIRMADA,
    ESTADO_EN_CONSTRUCCION,
    RESULTADO_CONFIRMADA,
    RESULTADO_CUPO_LLENO,
    RESULTADO_NO_EN_CONSTRUCCION,
    RESULTADO_SIN_HORARIO,
    RESULTADO_TOPE_CLIENTE,
    Citas,
)
from pedidos import Pedidos

PERFIL = "perfil_prueba"
CLIENTE = "573001112233"
DESDE = "2026-11-23 00:00"  # "ahora" de referencia para contar citas futuras


def _citas(tmp_path):
    return Citas(tmp_path / "bot.db")


def _cita_con_horario(citas, inicio="2026-11-24 08:00", numero=CLIENTE, ahora=1000.0):
    cita_id = citas.crear_en_construccion(numero, PERFIL, ahora)
    citas.fijar_fecha(cita_id, inicio[:10], "hora", ahora)
    citas.fijar_inicio(cita_id, inicio, "confirmacion", ahora)
    return cita_id


def _confirmar(citas, cita_id, cupos=1, tope=3):
    return citas.confirmar(cita_id, cupos, tope, DESDE, 2000.0)


def test_crear_en_construccion_cancela_la_anterior_del_mismo_numero(tmp_path):
    citas = _citas(tmp_path)
    primera = citas.crear_en_construccion(CLIENTE, PERFIL, 1000.0)

    segunda = citas.crear_en_construccion(CLIENTE, PERFIL, 1001.0)

    assert citas.obtener(primera)["estado"] == ESTADO_CANCELADA
    assert citas.obtener_en_construccion(CLIENTE)["id"] == segunda
    assert citas.obtener(segunda)["paso"] == "dia"


def test_pasos_fecha_hora_consentimiento_y_datos(tmp_path):
    citas = _citas(tmp_path)
    cita_id = citas.crear_en_construccion(CLIENTE, PERFIL, 1000.0)

    citas.fijar_fecha(cita_id, "2026-11-24", "hora", 1001.0)
    citas.fijar_inicio(cita_id, "2026-11-24 08:00", "consentimiento", 1002.0)
    citas.registrar_consentimiento(cita_id, "dato:nombre", 1003.0)
    citas.guardar_dato(cita_id, "nombre", "Persona de prueba", "dato:motivo", 1004.0)
    citas.guardar_dato(cita_id, "motivo", "Control general", "confirmacion", 1005.0)

    cita = citas.obtener(cita_id)
    assert cita["fecha"] == "2026-11-24"
    assert cita["inicio"] == "2026-11-24 08:00"
    assert cita["consentimiento_en"] == 1003.0
    assert cita["datos"] == {"nombre": "Persona de prueba", "motivo": "Control general"}
    assert cita["paso"] == "confirmacion"
    assert cita["actualizado_en"] == 1005.0


def test_cambiar_de_dia_borra_la_hora_elegida(tmp_path):
    citas = _citas(tmp_path)
    cita_id = _cita_con_horario(citas)

    citas.fijar_fecha(cita_id, "2026-11-25", "hora", 1010.0)

    assert citas.obtener(cita_id)["inicio"] is None


def test_confirmar_y_doble_confirmacion_no_duplica(tmp_path):
    citas = _citas(tmp_path)
    cita_id = _cita_con_horario(citas)

    assert _confirmar(citas, cita_id) == RESULTADO_CONFIRMADA
    assert _confirmar(citas, cita_id) == RESULTADO_NO_EN_CONSTRUCCION
    assert citas.obtener(cita_id)["estado"] == ESTADO_CONFIRMADA
    assert citas.ocupacion(PERFIL, DESDE, "2026-12-31 23:59") == {"2026-11-24 08:00": 1}


def test_no_se_confirma_sin_horario_ni_despues_de_confirmada(tmp_path):
    citas = _citas(tmp_path)
    cita_id = citas.crear_en_construccion(CLIENTE, PERFIL, 1000.0)

    assert _confirmar(citas, cita_id) == RESULTADO_SIN_HORARIO
    assert _confirmar(citas, 9999) == RESULTADO_NO_EN_CONSTRUCCION


def test_cupo_lleno_con_uno_y_con_varios_cupos(tmp_path):
    citas = _citas(tmp_path)
    numeros = [f"57300000000{i}" for i in range(4)]
    ids = [_cita_con_horario(citas, numero=n) for n in numeros]

    assert _confirmar(citas, ids[0], cupos=1) == RESULTADO_CONFIRMADA
    assert _confirmar(citas, ids[1], cupos=1) == RESULTADO_CUPO_LLENO
    assert _confirmar(citas, ids[1], cupos=3) == RESULTADO_CONFIRMADA
    assert _confirmar(citas, ids[2], cupos=3) == RESULTADO_CONFIRMADA
    assert _confirmar(citas, ids[3], cupos=3) == RESULTADO_CUPO_LLENO
    assert citas.obtener(ids[3])["estado"] == ESTADO_EN_CONSTRUCCION


def test_tope_de_citas_futuras_por_cliente_sin_contar_las_pasadas(tmp_path):
    citas = _citas(tmp_path)
    pasada = _cita_con_horario(citas, inicio="2026-11-20 08:00")
    assert _confirmar(citas, pasada) == RESULTADO_CONFIRMADA
    for hora in ("08:00", "08:30", "09:00"):
        assert _confirmar(citas, _cita_con_horario(citas, inicio=f"2026-11-24 {hora}")) == RESULTADO_CONFIRMADA

    cuarta = _cita_con_horario(citas, inicio="2026-11-24 09:30")

    assert _confirmar(citas, cuarta, tope=3) == RESULTADO_TOPE_CLIENTE
    assert citas.contar_futuras_del_cliente(CLIENTE, PERFIL, DESDE) == 3
    # Otro cliente no se ve afectado por el tope de este.
    assert _confirmar(citas, _cita_con_horario(citas, inicio="2026-11-24 09:30", numero="573009998877")) == (
        RESULTADO_CONFIRMADA
    )


def test_dos_reservas_simultaneas_del_mismo_cupo_nunca_lo_sobrepasan(tmp_path):
    for cupos in (1, 3):
        citas = Citas(tmp_path / f"concurrencia_{cupos}.db")
        ids = [_cita_con_horario(citas, numero=f"5730000001{i:02d}") for i in range(10)]
        resultados = []
        barrera = threading.Barrier(len(ids))

        def reservar(cita_id):
            barrera.wait()
            resultados.append(_confirmar(citas, cita_id, cupos=cupos))

        hilos = [threading.Thread(target=reservar, args=(cita_id,)) for cita_id in ids]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        assert resultados.count(RESULTADO_CONFIRMADA) == cupos
        assert resultados.count(RESULTADO_CUPO_LLENO) == len(ids) - cupos
        assert citas.ocupacion(PERFIL, DESDE, "2026-12-31 23:59") == {"2026-11-24 08:00": cupos}


def test_ocupacion_cuenta_solo_confirmadas_del_perfil_y_del_rango(tmp_path):
    citas = _citas(tmp_path)
    _confirmar(citas, _cita_con_horario(citas, inicio="2026-11-24 08:00"))
    _confirmar(citas, _cita_con_horario(citas, inicio="2026-11-24 08:00", numero="573009998877"), cupos=2)
    _cita_con_horario(citas, inicio="2026-11-24 08:30", numero="573001110000")  # en construcción
    otra_perfil = citas.crear_en_construccion("573002220000", "otro_perfil", 1000.0)
    citas.fijar_inicio(otra_perfil, "2026-11-24 09:00", "confirmacion", 1000.0)
    _confirmar(citas, otra_perfil)
    _confirmar(citas, _cita_con_horario(citas, inicio="2026-12-30 08:00", numero="573003330000"))

    assert citas.ocupacion(PERFIL, "2026-11-24 00:00", "2026-11-24 23:59") == {"2026-11-24 08:00": 2}


def test_listar_proximas_ordenadas_paginadas_y_sin_pasadas_ni_canceladas(tmp_path):
    citas = _citas(tmp_path)
    inicios = ["2026-11-26 10:00", "2026-11-24 08:00", "2026-11-25 09:00", "2026-11-20 08:00"]
    ids = {}
    for i, inicio in enumerate(inicios):
        ids[inicio] = _cita_con_horario(citas, inicio=inicio, numero=f"57300000020{i}")
        _confirmar(citas, ids[inicio])
    citas.cancelar(ids["2026-11-25 09:00"], 3000.0)

    proximas = citas.listar_proximas(PERFIL, DESDE)

    assert [c["inicio"] for c in proximas] == ["2026-11-24 08:00", "2026-11-26 10:00"]
    assert [c["inicio"] for c in citas.listar_proximas(PERFIL, DESDE, 1, 1)] == ["2026-11-26 10:00"]
    assert citas.listar_proximas("otro_perfil", DESDE) == []


def test_cancelar_libera_el_cupo_y_no_cancela_dos_veces(tmp_path):
    citas = _citas(tmp_path)
    cita_id = _cita_con_horario(citas)
    _confirmar(citas, cita_id)

    assert citas.cancelar(cita_id, 3000.0) is True
    assert citas.cancelar(cita_id, 3001.0) is False
    assert citas.cancelar(9999, 3001.0) is False
    assert citas.ocupacion(PERFIL, DESDE, "2026-12-31 23:59") == {}
    assert _confirmar(citas, _cita_con_horario(citas, numero="573009998877")) == RESULTADO_CONFIRMADA


def test_las_escrituras_del_flujo_no_tocan_una_cita_ya_confirmada(tmp_path):
    citas = _citas(tmp_path)
    cita_id = _cita_con_horario(citas)
    _confirmar(citas, cita_id)

    assert citas.fijar_inicio(cita_id, "2026-11-24 09:00", "confirmacion", 3000.0) is False
    assert citas.guardar_dato(cita_id, "nombre", "x", "confirmacion", 3000.0) is False
    assert citas.obtener(cita_id)["inicio"] == "2026-11-24 08:00"


def test_wamid_del_aviso_se_asocia_a_la_cita(tmp_path):
    citas = _citas(tmp_path)
    cita_id = _cita_con_horario(citas)

    citas.fijar_wamid_aviso(cita_id, "wamid.cita")

    assert citas.cita_por_wamid_aviso("wamid.cita") == cita_id
    assert citas.cita_por_wamid_aviso("wamid.otro") is None


def test_retencion_borra_datos_personales_y_conserva_fecha_y_hora(tmp_path):
    citas = _citas(tmp_path)
    vieja = _cita_con_horario(citas, inicio="2026-10-01 08:00", ahora=100.0)
    citas.guardar_dato(vieja, "nombre", "Persona de prueba", "confirmacion", 100.0)
    _confirmar(citas, vieja)
    futura = _cita_con_horario(citas, inicio="2026-12-01 08:00", numero="573009998877")
    citas.guardar_dato(futura, "nombre", "Otra persona", "confirmacion", 1000.0)
    _confirmar(citas, futura)
    abandonada = citas.crear_en_construccion("573001110000", PERFIL, 100.0)
    citas.guardar_dato(abandonada, "nombre", "Sin confirmar", "dato:motivo", 100.0)
    reciente = citas.crear_en_construccion("573002220000", PERFIL, 5000.0)
    citas.guardar_dato(reciente, "nombre", "En curso", "dato:motivo", 5000.0)

    borradas = citas.borrar_datos_vencidos(PERFIL, limite_inicio="2026-10-24 00:00", limite_actualizado=1000.0)

    assert borradas == 2
    cita_vieja = citas.obtener(vieja)
    assert cita_vieja["datos"] == {} and cita_vieja["numero_cliente"] == ""
    assert cita_vieja["inicio"] == "2026-10-01 08:00" and cita_vieja["estado"] == ESTADO_CONFIRMADA
    assert citas.obtener(abandonada)["datos"] == {}
    assert citas.obtener(futura)["datos"] == {"nombre": "Otra persona"}
    assert citas.obtener(reciente)["datos"] == {"nombre": "En curso"}
    # Idempotente: una segunda pasada no vuelve a contar las ya anonimizadas.
    assert citas.borrar_datos_vencidos(PERFIL, "2026-10-24 00:00", 1000.0) == 0


def test_comparte_el_archivo_de_base_con_pedidos_sin_interferir(tmp_path):
    ruta = tmp_path / "bot.db"
    pedidos = Pedidos(ruta)
    citas = Citas(ruta)
    pedido_id = pedidos.crear_en_construccion(CLIENTE, PERFIL, 1000.0)
    cita_id = _cita_con_horario(citas)

    assert pedidos.obtener(pedido_id)["estado"] == "en_construccion"
    assert citas.obtener(cita_id)["estado"] == ESTADO_EN_CONSTRUCCION
    Pedidos(ruta)  # reabrir no rompe nada
    Citas(ruta)
