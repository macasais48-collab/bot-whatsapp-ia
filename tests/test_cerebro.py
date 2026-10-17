import json
from datetime import date, datetime, timedelta

import holidays
import pytest

from cerebro import DIAS_SEMANA_ES, ZONA_BOGOTA, Cerebro, MENSAJE_SEGURO
from historial import HistorialMemoria
from llm.base import ProveedorIA


class FakeProveedor(ProveedorIA):
    def __init__(self, salida):
        self.salida = salida
        self.ultima_llamada = None

    def responder(self, sistema, mensajes):
        self.ultima_llamada = (sistema, mensajes)
        if isinstance(self.salida, Exception):
            raise self.salida
        return self.salida


def test_responde_con_json_valido_y_guarda_el_turno_en_el_historial():
    fake = FakeProveedor(json.dumps({"respuesta": "Abrimos a las 6am", "derivar": False}))
    historial = HistorialMemoria()
    cerebro = Cerebro(fake, historial)

    respuesta = cerebro.responder("conv1", "¿A qué hora abren?")

    assert respuesta.texto == "Abrimos a las 6am"
    assert respuesta.derivar is False
    assert historial.obtener("conv1", 10) == [
        {"role": "user", "content": "¿A qué hora abren?"},
        {"role": "assistant", "content": "Abrimos a las 6am"},
    ]


def test_usa_mensaje_seguro_si_la_salida_no_es_json():
    fake = FakeProveedor("esto no es json")
    cerebro = Cerebro(fake, HistorialMemoria())

    respuesta = cerebro.responder("conv1", "hola")

    assert respuesta.texto == MENSAJE_SEGURO
    assert respuesta.derivar is True


def test_usa_mensaje_seguro_si_el_json_no_tiene_la_forma_esperada():
    fake = FakeProveedor(json.dumps({"algo": "distinto"}))
    cerebro = Cerebro(fake, HistorialMemoria())

    respuesta = cerebro.responder("conv1", "hola")

    assert respuesta.texto == MENSAJE_SEGURO
    assert respuesta.derivar is True


def test_usa_mensaje_seguro_si_falla_la_llamada_al_proveedor_de_ia():
    fake = FakeProveedor(RuntimeError("fallo de red simulado"))
    cerebro = Cerebro(fake, HistorialMemoria())

    respuesta = cerebro.responder("conv1", "hola")

    assert respuesta.texto == MENSAJE_SEGURO
    assert respuesta.derivar is True


def test_el_prompt_de_sistema_incluye_la_informacion_del_negocio():
    fake = FakeProveedor(json.dumps({"respuesta": "ok", "derivar": False}))
    cerebro = Cerebro(fake, HistorialMemoria())

    cerebro.responder("conv1", "hola")

    sistema, _ = fake.ultima_llamada
    assert "Panadería San Roque" in sistema


def test_respeta_max_turnos_historial_de_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("MAX_TURNOS_HISTORIAL", "2")

    historial = HistorialMemoria()
    for i in range(4):
        historial.agregar("conv1", "user", f"mensaje previo {i}")

    fake = FakeProveedor(json.dumps({"respuesta": "ok", "derivar": False}))
    cerebro = Cerebro(fake, historial)

    cerebro.responder("conv1", "mensaje nuevo")

    _, mensajes_enviados = fake.ultima_llamada
    assert mensajes_enviados == [
        {"role": "user", "content": "mensaje previo 2"},
        {"role": "user", "content": "mensaje previo 3"},
        {"role": "user", "content": "mensaje nuevo"},
    ]


def test_max_turnos_historial_invalido_no_filtra_su_valor_en_el_error(monkeypatch):
    valor_secreto = "no-es-un-numero-sk-ant-usr-xyz"
    monkeypatch.setenv("MAX_TURNOS_HISTORIAL", valor_secreto)

    fake = FakeProveedor(json.dumps({"respuesta": "ok", "derivar": False}))

    with pytest.raises(ValueError) as info:
        Cerebro(fake, HistorialMemoria())

    assert valor_secreto not in str(info.value)


def _reloj_fijo(fecha_hora: datetime):
    return lambda: fecha_hora


def test_contexto_de_fecha_en_un_dia_normal_no_festivo():
    ancla = datetime(2026, 9, 1, 10, 0, tzinfo=ZONA_BOGOTA)
    martes = ancla + timedelta(days=(1 - ancla.weekday()) % 7)
    assert martes.weekday() == 1  # martes
    assert martes.date() not in holidays.Colombia()
    assert (martes.date() + timedelta(days=1)) not in holidays.Colombia()

    fake = FakeProveedor(json.dumps({"respuesta": "ok", "derivar": False}))
    cerebro = Cerebro(fake, HistorialMemoria(), reloj=_reloj_fijo(martes))

    cerebro.responder("conv1", "¿A qué hora abren mañana?")

    sistema, _ = fake.ultima_llamada
    assert f"Hoy es {DIAS_SEMANA_ES[martes.weekday()]}, {martes.date().isoformat()}" in sistema
    assert "Hoy no es festivo en Colombia." in sistema
    assert "Mañana no es festivo en Colombia." in sistema


def test_contexto_de_fecha_en_domingo():
    ancla = datetime(2026, 9, 1, 10, 0, tzinfo=ZONA_BOGOTA)
    domingo = ancla + timedelta(days=(6 - ancla.weekday()) % 7)
    assert domingo.weekday() == 6  # domingo

    fake = FakeProveedor(json.dumps({"respuesta": "ok", "derivar": False}))
    cerebro = Cerebro(fake, HistorialMemoria(), reloj=_reloj_fijo(domingo))

    cerebro.responder("conv1", "hola")

    sistema, _ = fake.ultima_llamada
    assert f"Hoy es {DIAS_SEMANA_ES[domingo.weekday()]}, {domingo.date().isoformat()}" in sistema


def test_contexto_de_fecha_en_festivo_colombiano_20_de_julio():
    festivo = datetime(2026, 7, 20, 10, 0, tzinfo=ZONA_BOGOTA)
    assert festivo.date() in holidays.Colombia()  # verificación independiente de la librería

    fake = FakeProveedor(json.dumps({"respuesta": "ok", "derivar": False}))
    cerebro = Cerebro(fake, HistorialMemoria(), reloj=_reloj_fijo(festivo))

    cerebro.responder("conv1", "hola")

    sistema, _ = fake.ultima_llamada
    assert f"Hoy es {DIAS_SEMANA_ES[festivo.weekday()]}, {festivo.date().isoformat()}" in sistema
    assert "Hoy es festivo en Colombia." in sistema


def test_contexto_de_fecha_incluye_un_festivo_dentro_de_los_proximos_90_dias():
    ahora = datetime(2026, 10, 16, 10, 0, tzinfo=ZONA_BOGOTA)
    festivo_lejano = date(2026, 11, 2)
    nombre_festivo = holidays.Colombia().get(festivo_lejano)
    assert nombre_festivo is not None  # verificación independiente: sí es festivo
    assert (festivo_lejano - ahora.date()).days <= 90

    fake = FakeProveedor(json.dumps({"respuesta": "ok", "derivar": False}))
    cerebro = Cerebro(fake, HistorialMemoria(), reloj=_reloj_fijo(ahora))

    cerebro.responder("conv1", "¿el lunes 2 de noviembre atienden?")

    sistema, _ = fake.ultima_llamada
    nombre_limpio = nombre_festivo.replace(" (observado)", "")
    assert f"{festivo_lejano.isoformat()} {DIAS_SEMANA_ES[festivo_lejano.weekday()]} ({nombre_limpio})" in sistema
    assert "aplica el horario de festivos del negocio" in sistema
    assert "observado" not in sistema.lower()
