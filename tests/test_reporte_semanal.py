import logging
import threading
from datetime import datetime

import pytest

import reporte_semanal
from pedidos import ENTREGA_EN_PREPARACION, ENTREGA_ENTREGADO, Pedidos
from reporte_semanal import ZONA_BOGOTA

NUMERO_DUENO = "573005554433"


def _ts(anio, mes, dia, hora=0, minuto=0):
    return datetime(anio, mes, dia, hora, minuto, tzinfo=ZONA_BOGOTA).timestamp()


# Miércoles 11/11/2026, 10:00 en Bogotá: semana en curso desde el lunes 09/11
# (ISO 2026-W46); la semana anterior es del lunes 02/11 al domingo 08/11 (W45).
AHORA = _ts(2026, 11, 11, 10)


class EnviosConWamidFalsos:
    def __init__(self, ok=True):
        self.ok = ok
        self.llamadas = []

    def __call__(self, numero, texto):
        self.llamadas.append((numero, texto))
        return (True, f"wamid.reporte-{len(self.llamadas)}") if self.ok else (False, None)


class PlantillasFalsas:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, nombre, idioma, parametros, botones=None):
        self.llamadas.append((numero, nombre, idioma, parametros, botones))
        return True, "wamid.plantilla-reporte"


@pytest.fixture
def pedidos(tmp_path):
    return Pedidos(tmp_path / "pedidos.db")


def _pedido(pedidos, creado_en, items, total, metodo="efectivo", entrega="recoger",
            entregado=False, numero="573001112233", direccion=None):
    pedido_id = pedidos.crear_en_construccion(numero, "tamales", ahora=creado_en)
    for clave, nombre, cantidad in items:
        pedidos.agregar_item(pedido_id, clave, nombre, 1000, cantidad, ahora=creado_en)
    if entrega == "domicilio":
        pedidos.fijar_entrega(
            pedido_id, "domicilio", ahora=creado_en, paso_siguiente="confirmacion",
            zona_domicilio="centro", direccion_texto=direccion,
        )
    else:
        pedidos.fijar_entrega(pedido_id, "recoger", ahora=creado_en, paso_siguiente="confirmacion")
    if metodo == "efectivo":
        pedidos.confirmar_efectivo(pedido_id, total=total, ahora=creado_en)
    else:
        pedidos.marcar_pago_pendiente(pedido_id, total=total, ahora=creado_en)
        pedidos.marcar_pago_por_verificar(pedido_id, ahora=creado_en)
        pedidos.marcar_pagado(pedido_id, ahora=creado_en)
    if entregado:
        siguiente = "en_camino" if entrega == "domicilio" else "listo_para_recoger"
        pedidos.avanzar_estado_entrega(pedido_id, ENTREGA_EN_PREPARACION, siguiente, ahora=creado_en)
        pedidos.avanzar_estado_entrega(pedido_id, siguiente, ENTREGA_ENTREGADO, ahora=creado_en)
    return pedido_id


def _semana_de_ejemplo(pedidos):
    """Semana anterior (02/11 a 08/11) con 4 pedidos confirmados, uno sin
    confirmar y uno de otra semana — ninguno de esos dos debe contar."""
    _pedido(pedidos, _ts(2026, 11, 2, 9), [("a", "Producto A", 3), ("b", "Producto B", 1)], 30000,
            metodo="efectivo", entrega="domicilio", entregado=True, direccion="Calle 10 #5-23")
    _pedido(pedidos, _ts(2026, 11, 4, 12), [("a", "Producto A", 2)], 20000,
            metodo="qr", entrega="recoger", entregado=True)
    _pedido(pedidos, _ts(2026, 11, 6, 18), [("c", "Producto C", 2), ("b", "Producto B", 1)], 15000,
            metodo="qr", entrega="domicilio", entregado=False)
    _pedido(pedidos, _ts(2026, 11, 8, 23, 59), [("d", "Producto D", 1)], 5000,
            metodo="efectivo", entrega="recoger", entregado=True)
    # No cuentan: un pedido todavía en pago y uno de la semana en curso.
    en_pago = pedidos.crear_en_construccion("573001112233", "tamales", ahora=_ts(2026, 11, 5))
    pedidos.marcar_pago_pendiente(en_pago, total=99000, ahora=_ts(2026, 11, 5))
    _pedido(pedidos, _ts(2026, 11, 9, 0, 1), [("a", "Producto A", 10)], 50000)


# -- Fechas y programación --


def test_semana_anterior_es_de_lunes_a_domingo_en_hora_de_bogota():
    desde, hasta, clave, etiqueta = reporte_semanal.semana_anterior(AHORA)

    assert desde == _ts(2026, 11, 2)
    assert hasta == _ts(2026, 11, 9)
    assert clave == "2026-W45"
    assert etiqueta == "02/11/2026 al 08/11/2026"


def test_semana_anterior_al_cambio_de_anio_usa_la_semana_iso():
    _, _, clave, etiqueta = reporte_semanal.semana_anterior(_ts(2026, 1, 5, 8))

    assert clave == "2026-W01"
    assert etiqueta == "29/12/2025 al 04/01/2026"


@pytest.mark.parametrize(
    "dia, hora, esperado",
    [
        (None, None, (0, 8, 0)),
        ("", "", (0, 8, 0)),
        ("Miércoles", "18:30", (2, 18, 30)),
        ("domingo", "7", (6, 7, 0)),
        ("SABADO", "00:00", (5, 0, 0)),
    ],
)
def test_leer_programacion_validos(dia, hora, esperado):
    assert reporte_semanal.leer_programacion(dia, hora) == esperado


@pytest.mark.parametrize("dia, hora", [("lunez", "8"), ("lunes", "25"), ("lunes", "8:75"), ("lunes", "ocho")])
def test_leer_programacion_invalida_usa_el_valor_por_defecto_y_advierte(dia, hora, caplog):
    caplog.set_level(logging.WARNING, logger="reporte_semanal")

    dia_leido, hora_leida, minuto_leido = reporte_semanal.leer_programacion(dia, hora)

    assert dia_leido == 0
    assert (hora_leida, minuto_leido) in ((8, 0),)
    assert caplog.records


# -- Cálculo --


def test_calculo_del_reporte_con_datos_de_ejemplo(pedidos):
    _semana_de_ejemplo(pedidos)
    desde, hasta, _, _ = reporte_semanal.semana_anterior(AHORA)

    reporte = reporte_semanal.calcular_reporte(pedidos, desde, hasta)

    assert reporte["pedidos"] == 4
    assert reporte["ventas"] == 70000
    assert reporte["por_metodo"] == {
        "efectivo": {"pedidos": 2, "ventas": 35000},
        "qr": {"pedidos": 2, "ventas": 35000},
    }
    assert reporte["por_entrega"] == {"domicilio": 2, "recoger": 2}
    assert reporte["productos_top"] == [("Producto A", 5), ("Producto B", 2), ("Producto C", 2)]
    assert reporte["entregados"] == 3
    assert reporte["pendientes"] == 1


def test_texto_del_reporte_con_datos_de_ejemplo(pedidos):
    _semana_de_ejemplo(pedidos)
    desde, hasta, _, _ = reporte_semanal.semana_anterior(AHORA)

    texto = reporte_semanal.texto_reporte(reporte_semanal.calcular_reporte(pedidos, desde, hasta), "Titulo")

    assert texto == (
        "Titulo\n"
        "Pedidos confirmados: 4\n"
        "Ventas totales: $70.000\n"
        "Por método de pago: Efectivo 2 ($35.000), QR / transferencia 2 ($35.000)\n"
        "Por forma de entrega: Domicilio 2, Recoger en el local 2\n"
        "Productos más vendidos: 5 x Producto A, 2 x Producto B, 2 x Producto C\n"
        "Entregas: 3 entregados y 1 pendiente"
    )


def test_semana_sin_pedidos(pedidos):
    desde, hasta, _, etiqueta = reporte_semanal.semana_anterior(AHORA)

    reporte = reporte_semanal.calcular_reporte(pedidos, desde, hasta)
    texto = reporte_semanal.texto_reporte(reporte, "Titulo")
    variables = reporte_semanal.variables_plantilla(reporte, etiqueta)

    assert reporte["pedidos"] == 0 and reporte["ventas"] == 0
    assert "Pedidos confirmados: 0" in texto
    assert "Ventas totales: $0" in texto
    assert "Productos más vendidos: ninguno" in texto
    assert "0 entregados y 0 pendientes" in texto
    assert all(v.strip() for v in variables)  # Meta no acepta variables vacías


def test_variables_de_plantilla_en_una_sola_linea(pedidos):
    _semana_de_ejemplo(pedidos)
    desde, hasta, _, etiqueta = reporte_semanal.semana_anterior(AHORA)

    variables = reporte_semanal.variables_plantilla(reporte_semanal.calcular_reporte(pedidos, desde, hasta), etiqueta)

    assert len(variables) == 7
    assert variables[0] == "02/11/2026 al 08/11/2026"
    assert variables[1] == "4"
    assert variables[2] == "$70.000"
    for variable in variables:
        assert "\n" not in variable and "\t" not in variable and "    " not in variable


def test_el_reporte_nunca_contiene_telefonos_ni_direcciones(pedidos):
    _semana_de_ejemplo(pedidos)
    desde, hasta, _, etiqueta = reporte_semanal.semana_anterior(AHORA)
    reporte = reporte_semanal.calcular_reporte(pedidos, desde, hasta)

    contenido = (
        repr(reporte)
        + reporte_semanal.texto_reporte(reporte, "x")
        + repr(reporte_semanal.variables_plantilla(reporte, etiqueta))
        + reporte_semanal.texto_semana_en_curso(pedidos, AHORA)
    )

    assert "573001112233" not in contenido
    assert "2233" not in contenido
    assert "Calle 10" not in contenido


def test_semana_en_curso_cuenta_desde_el_lunes_hasta_ahora(pedidos):
    _semana_de_ejemplo(pedidos)

    texto = reporte_semanal.texto_semana_en_curso(pedidos, AHORA)

    assert texto.startswith("Reporte de la semana en curso (desde el lunes 09/11/2026)")
    assert "Pedidos confirmados: 1" in texto
    assert "10 x Producto A" in texto


@pytest.mark.parametrize("texto", ["reporte", "Reporte", " REPORTE ", "repórte"])
def test_palabra_clave_reporte(texto):
    assert reporte_semanal.es_palabra_clave_reporte(texto)


@pytest.mark.parametrize("texto", ["reportes", "el reporte", "", None])
def test_otros_textos_no_son_la_palabra_reporte(texto):
    assert not reporte_semanal.es_palabra_clave_reporte(texto)


# -- Envío automático --


def test_envio_por_texto_libre_registra_la_semana_y_el_wamid(pedidos):
    _semana_de_ejemplo(pedidos)
    envios = EnviosConWamidFalsos()

    enviado = reporte_semanal.enviar_reporte_semana_anterior(pedidos, NUMERO_DUENO, AHORA, envios)

    assert enviado is True
    assert envios.llamadas[0][0] == NUMERO_DUENO
    assert envios.llamadas[0][1].startswith("Reporte semanal del 02/11/2026 al 08/11/2026")
    assert pedidos.reporte_enviado("2026-W45")
    assert pedidos.semana_reporte_por_wamid("wamid.reporte-1") == "2026-W45"


def test_envio_por_plantilla_si_esta_configurada(pedidos):
    _semana_de_ejemplo(pedidos)
    envios = EnviosConWamidFalsos()
    plantillas = PlantillasFalsas()

    reporte_semanal.enviar_reporte_semana_anterior(
        pedidos, NUMERO_DUENO, AHORA, envios,
        enviar_plantilla_fn=plantillas, plantilla_nombre="reporte_semanal", plantilla_idioma="es",
    )

    assert envios.llamadas == []
    numero, nombre, idioma, parametros, botones = plantillas.llamadas[0]
    assert (numero, nombre, idioma, botones) == (NUMERO_DUENO, "reporte_semanal", "es", None)
    assert len(parametros) == 7
    assert pedidos.semana_reporte_por_wamid("wamid.plantilla-reporte") == "2026-W45"


def test_la_misma_semana_nunca_se_envia_dos_veces(pedidos):
    envios = EnviosConWamidFalsos()

    primero = reporte_semanal.enviar_reporte_semana_anterior(pedidos, NUMERO_DUENO, AHORA, envios)
    segundo = reporte_semanal.enviar_reporte_semana_anterior(pedidos, NUMERO_DUENO, AHORA + 60, envios)

    assert (primero, segundo) == (True, False)
    assert len(envios.llamadas) == 1


def test_si_el_envio_falla_se_libera_la_semana_para_reintentar(pedidos):
    fallido = reporte_semanal.enviar_reporte_semana_anterior(
        pedidos, NUMERO_DUENO, AHORA, EnviosConWamidFalsos(ok=False)
    )

    assert fallido is False
    assert not pedidos.reporte_enviado("2026-W45")
    assert reporte_semanal.enviar_reporte_semana_anterior(pedidos, NUMERO_DUENO, AHORA, EnviosConWamidFalsos())


def test_sin_numero_dueno_no_se_envia_nada(pedidos):
    envios = EnviosConWamidFalsos()

    assert reporte_semanal.enviar_reporte_semana_anterior(pedidos, None, AHORA, envios) is False
    assert envios.llamadas == []
    assert not pedidos.reporte_enviado("2026-W45")


# -- Recuperación al arrancar --


def _recuperar(pedidos, ahora, envios, dia=0, hora=8, minuto=0):
    return reporte_semanal.recuperar_reporte_pendiente(
        pedidos, ahora, dia, hora, minuto, numero_dueno=NUMERO_DUENO, enviar_texto_con_wamid_fn=envios,
    )


def test_recuperacion_al_arrancar_envia_el_reporte_de_la_semana_anterior_si_falta(pedidos):
    envios = EnviosConWamidFalsos()

    assert _recuperar(pedidos, AHORA, envios) is True  # miércoles, ya pasó el lunes 8:00
    assert pedidos.reporte_enviado("2026-W45")
    assert len(envios.llamadas) == 1


def test_recuperacion_no_repite_un_reporte_ya_enviado(pedidos):
    envios = EnviosConWamidFalsos()
    reporte_semanal.enviar_reporte_semana_anterior(pedidos, NUMERO_DUENO, _ts(2026, 11, 9, 8), envios)

    assert _recuperar(pedidos, AHORA, envios) is False
    assert len(envios.llamadas) == 1


def test_recuperacion_antes_de_la_hora_programada_no_envia_nada(pedidos):
    envios = EnviosConWamidFalsos()

    # Lunes 7:30: todavía no es la hora programada (8:00); lo enviará el programador.
    assert _recuperar(pedidos, _ts(2026, 11, 9, 7, 30), envios) is False
    # Miércoles 10:00 con el reporte programado para el viernes: tampoco.
    assert _recuperar(pedidos, AHORA, envios, dia=4, hora=9) is False
    assert envios.llamadas == []


# -- Programador --


def test_el_programador_agenda_la_tarea_semanal_y_ejecuta_la_recuperacion_de_inmediato():
    recuperacion_ejecutada = threading.Event()

    programador = reporte_semanal.iniciar_programador(
        tarea_semanal=lambda: None,
        tarea_recuperacion=recuperacion_ejecutada.set,
        dia=2, hora=18, minuto=30,
    )
    try:
        assert recuperacion_ejecutada.wait(timeout=5)
        trabajo = programador.get_job("reporte_semanal")
        siguiente = trabajo.next_run_time.astimezone(ZONA_BOGOTA)
        assert (siguiente.weekday(), siguiente.hour, siguiente.minute) == (2, 18, 30)
    finally:
        programador.shutdown(wait=False)
