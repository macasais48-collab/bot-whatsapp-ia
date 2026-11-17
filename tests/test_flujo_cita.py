import logging
from datetime import date, datetime

import pytest

import flujo_cita
from agenda import ZONA_BOGOTA, validar_config_citas
from citas import ESTADO_CANCELADA, ESTADO_CONFIRMADA, ESTADO_EN_CONSTRUCCION, Citas
from flujo_cita import (
    MENSAJE_CANCELADA_POR_INACTIVIDAD,
    MENSAJE_CITA_CANCELADA,
    MENSAJE_ENTRADA_NO_RECONOCIDA,
    MENSAJE_HORARIO_NO_DISPONIBLE,
    MENSAJE_HORARIO_OCUPADO_AL_CONFIRMAR,
    MENSAJE_SIN_DISPONIBILIDAD,
    TEXTO_CONSENTIMIENTO,
    FlujoCita,
)
from pedidos import Pedidos

CLIENTE = "573001112233"
DUENO = "573005554433"
PERFIL = "perfil_prueba"
MENSAJE_DERIVACION = "Le comunico con una persona de nuestro equipo."
DATOS = [
    {"clave": "nombre", "pregunta": "¿A nombre de quién agendamos?", "etiqueta": "Nombre"},
    {"clave": "mascota", "pregunta": "¿Cómo se llama su mascota y qué especie es?", "etiqueta": "Mascota"},
    {"clave": "motivo", "pregunta": "¿Cuál es el motivo?", "etiqueta": "Motivo"},
]


def _reloj(anio, mes, dia, hora=20, minuto=0):
    return datetime(anio, mes, dia, hora, minuto, tzinfo=ZONA_BOGOTA).timestamp()


DOMINGO_NOCHE = _reloj(2026, 11, 22)  # domingo 22/11/2026, 8:00 p.m.


def _config(**cambios):
    base = {
        "duracion_minutos": 30,
        "horario": {d: [["08:00", "10:00"]] for d in ("lunes", "martes", "miercoles", "jueves", "viernes")},
        "dias_hacia_adelante": 6,
        "datos": DATOS,
        "telefono_negocio": "300 000 0000",
    }
    base.update(cambios)
    return validar_config_citas(base, "recursos_prueba.json")


class Envios:
    def __init__(self, con_wamid=False, prefijo="wamid"):
        self.llamadas = []
        self._con_wamid = con_wamid
        self._prefijo = prefijo

    def __call__(self, *args, **kwargs):
        self.llamadas.append(args)
        if self._con_wamid:
            return True, f"{self._prefijo}-{len(self.llamadas)}"
        return True


class Escenario:
    def __init__(self, tmp_path, config=None, reloj=None, numero_dueno=DUENO, con_plantilla=False):
        self.ahora = {"valor": reloj if reloj is not None else DOMINGO_NOCHE}
        self.citas = Citas(tmp_path / "bot.db")
        self.pedidos = Pedidos(tmp_path / "bot.db")
        self.texto = Envios()
        self.botones = Envios()
        self.lista = Envios()
        self.con_wamid = Envios(con_wamid=True, prefijo="wamid-texto")
        self.plantilla = Envios(con_wamid=True, prefijo="wamid-plantilla")
        self.config = config or _config()
        self.flujo = FlujoCita(
            citas=self.citas,
            pedidos=self.pedidos,
            config=self.config,
            perfil=PERFIL,
            mensaje_derivacion=MENSAJE_DERIVACION,
            enviar_texto_fn=self.texto,
            enviar_botones_fn=self.botones,
            enviar_lista_fn=self.lista,
            enviar_texto_con_wamid_fn=self.con_wamid,
            reloj=lambda: self.ahora["valor"],
            numero_dueno=numero_dueno,
            enviar_plantilla_fn=self.plantilla,
            plantilla_aviso_cita_nombre="plantilla_cita" if con_plantilla else None,
            plantilla_aviso_cita_idioma="es" if con_plantilla else None,
        )

    def fila(self, id_fila, numero=CLIENTE):
        self.flujo.manejar_mensaje(numero, {"type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": id_fila, "title": "x"}}})

    def boton(self, id_boton, numero=CLIENTE):
        self.flujo.manejar_mensaje(numero, {"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": id_boton, "title": "x"}}})

    def escribir(self, texto, numero=CLIENTE):
        self.flujo.manejar_mensaje(numero, {"type": "text", "text": {"body": texto}})

    def filas_ultima_lista(self):
        return [fila for seccion in self.lista.llamadas[-1][3] for fila in seccion["filas"]]

    def hasta_confirmacion(self, numero=CLIENTE, dia="2026-11-23", hora="08:00"):
        self.fila(f"cita_dia_{dia}", numero)
        self.fila(f"cita_hora_{dia}_{hora}", numero)
        self.boton("cita_acepto", numero)
        self.escribir("Ana Prueba", numero)
        self.escribir("Toby, perro", numero)
        self.escribir("Vacunas", numero)

    def cita(self, numero=CLIENTE):
        return self.citas.obtener_en_construccion(numero)


# -- Ofrecer días y horas --


def test_ofrece_solo_los_dias_con_horas_libres(tmp_path):
    e = Escenario(tmp_path)

    assert e.flujo.ofrecer_dias(CLIENTE) is True

    filas = e.filas_ultima_lista()
    assert [f["id"] for f in filas] == [f"cita_dia_2026-11-{d}" for d in (23, 24, 25, 26, 27)]
    assert filas[0]["titulo"] == "Lun 23 nov"
    assert filas[0]["descripcion"] == "4 horarios libres"
    assert all(len(f["titulo"]) <= 24 for f in filas)


def test_sin_disponibilidad_avisa_y_no_manda_lista(tmp_path):
    e = Escenario(tmp_path, config=_config(dias_bloqueados=[f"2026-11-{d}" for d in range(23, 28)]))

    assert e.flujo.ofrecer_dias(CLIENTE) is False

    assert e.texto.llamadas == [(CLIENTE, MENSAJE_SIN_DISPONIBILIDAD)]
    assert e.lista.llamadas == []


def test_mas_de_10_dias_se_paginan_con_ver_mas(tmp_path):
    e = Escenario(tmp_path, config=_config(dias_hacia_adelante=20))

    e.flujo.ofrecer_dias(CLIENTE)
    primera = e.filas_ultima_lista()
    e.fila("cita_dias_pag_2")
    segunda = e.filas_ultima_lista()

    assert len(primera) == 10 and primera[-1]["titulo"] == "Ver más días"
    assert primera[-1]["id"] == "cita_dias_pag_2"
    assert segunda[0]["id"] == "cita_dia_2026-12-04"  # el 10.º día hábil, primero de la página 2
    assert len(set(f["id"] for f in primera) & set(f["id"] for f in segunda)) == 0


def test_elegir_dia_ofrece_sus_horas_y_la_opcion_de_otro_dia(tmp_path):
    e = Escenario(tmp_path)

    e.fila("cita_dia_2026-11-23")

    filas = e.filas_ultima_lista()
    assert [f["titulo"] for f in filas] == ["8:00 a.m.", "8:30 a.m.", "9:00 a.m.", "9:30 a.m.", "Elegir otro día"]
    assert e.cita()["paso"] == "hora"
    assert e.cita()["fecha"] == "2026-11-23"


def test_hoy_respeta_la_anticipacion_minima(tmp_path):
    e = Escenario(tmp_path, reloj=_reloj(2026, 11, 23, 7, 30))  # + 60 min = 8:30

    e.fila("cita_dia_2026-11-23")

    assert [f["titulo"] for f in e.filas_ultima_lista()][:2] == ["8:30 a.m.", "9:00 a.m."]


# -- Flujo completo --


def test_flujo_completo_con_aviso_al_dueno_por_texto_libre(tmp_path):
    e = Escenario(tmp_path)

    e.fila("cita_dia_2026-11-23")
    e.fila("cita_hora_2026-11-23_08:00")
    assert e.botones.llamadas[-1][1] == TEXTO_CONSENTIMIENTO
    assert [b["titulo"] for b in e.botones.llamadas[-1][2]] == ["Acepto", "No acepto"]
    e.boton("cita_acepto")
    assert e.texto.llamadas[-1] == (CLIENTE, DATOS[0]["pregunta"])
    e.escribir("Ana Prueba")
    e.escribir("Toby, perro")
    e.escribir("Vacunas")
    resumen = e.botones.llamadas[-1][1]
    assert "lunes 23 de noviembre, 8:00 a.m." in resumen
    assert "Nombre: Ana Prueba" in resumen and "Mascota: Toby, perro" in resumen
    cita_id = e.cita()["id"]

    e.boton("cita_confirmar")

    cita = e.citas.obtener(cita_id)
    assert cita["estado"] == ESTADO_CONFIRMADA
    assert cita["consentimiento_en"] == DOMINGO_NOCHE
    confirmacion = e.texto.llamadas[-1]
    assert confirmacion[0] == CLIENTE
    assert f"Su cita #{cita_id} quedó agendada para el lunes 23 de noviembre, 8:00 a.m." in confirmacion[1]
    assert "Motivo: Vacunas" in confirmacion[1]
    assert len(e.con_wamid.llamadas) == 1
    destino, aviso = e.con_wamid.llamadas[0]
    assert destino == DUENO
    assert f"Nueva cita #{cita_id}" in aviso and CLIENTE in aviso and "Toby, perro" in aviso
    assert e.citas.cita_por_wamid_aviso("wamid-texto-1") == cita_id
    assert e.plantilla.llamadas == []


def test_aviso_al_dueno_por_plantilla(tmp_path):
    e = Escenario(tmp_path, con_plantilla=True)
    e.hasta_confirmacion()
    cita_id = e.cita()["id"]

    e.boton("cita_confirmar")

    assert e.con_wamid.llamadas == []
    assert e.plantilla.llamadas == [
        (
            DUENO, "plantilla_cita", "es",
            [str(cita_id), "lunes 23 de noviembre, 8:00 a.m.",
             "Nombre: Ana Prueba; Mascota: Toby, perro; Motivo: Vacunas", CLIENTE],
        )
    ]
    assert e.citas.cita_por_wamid_aviso("wamid-plantilla-1") == cita_id


def test_sin_numero_dueno_confirma_sin_avisar(tmp_path):
    e = Escenario(tmp_path, numero_dueno=None)
    e.hasta_confirmacion()

    e.boton("cita_confirmar")

    assert "quedó agendada" in e.texto.llamadas[-1][1]
    assert e.con_wamid.llamadas == [] and e.plantilla.llamadas == []


def test_doble_toque_en_confirmar_no_duplica_nada(tmp_path):
    e = Escenario(tmp_path)
    e.hasta_confirmacion()
    e.boton("cita_confirmar")
    envios_previos = len(e.texto.llamadas)

    e.boton("cita_confirmar")

    assert len(e.texto.llamadas) == envios_previos
    assert len(e.con_wamid.llamadas) == 1


def test_cambiar_horario_conserva_datos_y_consentimiento(tmp_path):
    e = Escenario(tmp_path)
    e.hasta_confirmacion()

    e.boton("cita_cambiar")
    assert e.cita()["paso"] == "dia"
    e.fila("cita_dia_2026-11-24")
    e.fila("cita_hora_2026-11-24_09:30")

    assert e.cita()["paso"] == "confirmacion"
    assert "martes 24 de noviembre, 9:30 a.m." in e.botones.llamadas[-1][1]
    assert e.cita()["datos"]["nombre"] == "Ana Prueba"


# -- Disponibilidad al elegir y al confirmar --


def test_fila_de_hora_ocupada_nunca_se_acepta(tmp_path):
    e = Escenario(tmp_path)
    e.hasta_confirmacion(numero="573009998877")
    e.boton("cita_confirmar", numero="573009998877")
    e.fila("cita_dia_2026-11-23")

    e.fila("cita_hora_2026-11-23_08:00")  # fila de una lista anterior

    assert e.lista.llamadas[-1][1] == MENSAJE_HORARIO_NO_DISPONIBLE
    assert "8:00 a.m." not in [f["titulo"] for f in e.filas_ultima_lista()]
    assert e.cita()["inicio"] is None


def test_fila_manipulada_o_fuera_de_horario_no_se_acepta(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")

    e.fila("cita_hora_2026-11-23_08:15")

    assert e.lista.llamadas[-1][1] == MENSAJE_HORARIO_NO_DISPONIBLE
    assert e.cita()["inicio"] is None


def test_cupo_tomado_entre_la_lista_y_la_confirmacion(tmp_path):
    e = Escenario(tmp_path)
    e.hasta_confirmacion()
    e.hasta_confirmacion(numero="573009998877")  # otro cliente, mismo horario
    e.boton("cita_confirmar", numero="573009998877")  # y confirma primero

    e.boton("cita_confirmar")

    assert e.lista.llamadas[-1][1] == MENSAJE_HORARIO_OCUPADO_AL_CONFIRMAR
    assert e.cita()["estado"] == ESTADO_EN_CONSTRUCCION and e.cita()["paso"] == "hora"
    assert len(e.con_wamid.llamadas) == 1  # solo el aviso de la cita del otro cliente


def test_horario_vencido_mientras_el_cliente_tardaba(tmp_path):
    e = Escenario(tmp_path, reloj=_reloj(2026, 11, 23, 6, 59))  # 8:00 aún se puede (anticipación 60 min)
    e.hasta_confirmacion()
    e.ahora["valor"] = _reloj(2026, 11, 23, 7, 20)  # 21 min después: 8:00 ya está dentro de la anticipación

    e.boton("cita_confirmar")

    assert e.cita()["estado"] == ESTADO_EN_CONSTRUCCION
    assert e.lista.llamadas[-1][1] == MENSAJE_HORARIO_NO_DISPONIBLE
    assert e.con_wamid.llamadas == []


def test_tope_de_citas_por_cliente(tmp_path):
    e = Escenario(tmp_path, config=_config(max_citas_por_cliente=1))
    e.hasta_confirmacion()
    e.boton("cita_confirmar")
    e.hasta_confirmacion(dia="2026-11-24")

    e.boton("cita_confirmar")

    assert "Ya tiene 1 citas agendadas" in e.texto.llamadas[-1][1]
    assert e.cita() is None
    assert len(e.con_wamid.llamadas) == 1


# -- Consentimiento y datos --


def test_no_acepta_no_agenda_da_el_telefono_y_deriva(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")
    e.fila("cita_hora_2026-11-23_08:00")
    cita_id = e.cita()["id"]

    e.boton("cita_no_acepto")

    assert e.citas.obtener(cita_id)["estado"] == ESTADO_CANCELADA
    mensaje = e.texto.llamadas[-1][1]
    assert "no podemos agendar" in mensaje and "300 000 0000" in mensaje and MENSAJE_DERIVACION in mensaje
    destino, aviso = e.con_wamid.llamadas[-1]
    assert destino == DUENO and CLIENTE in aviso and "no autorizó el tratamiento de datos" in aviso


def test_no_acepta_sin_telefono_configurado(tmp_path):
    e = Escenario(tmp_path, config=_config(telefono_negocio=None))
    e.fila("cita_dia_2026-11-23")
    e.fila("cita_hora_2026-11-23_08:00")

    e.boton("cita_no_acepto")

    assert "llamarnos" not in e.texto.llamadas[-1][1]


def test_no_se_piden_datos_antes_de_aceptar(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")
    e.fila("cita_hora_2026-11-23_08:00")

    e.escribir("Ana Prueba")  # escribe en lugar de tocar un botón

    assert e.cita()["datos"] == {}
    assert e.texto.llamadas[-1][1] == MENSAJE_ENTRADA_NO_RECONOCIDA
    assert e.botones.llamadas[-1][1] == TEXTO_CONSENTIMIENTO


@pytest.mark.parametrize(
    "mensaje",
    [{"type": "text", "text": {"body": "   "}}, {"type": "image", "image": {"id": "x"}}],
)
def test_dato_vacio_o_que_no_es_texto_se_vuelve_a_pedir(tmp_path, mensaje):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")
    e.fila("cita_hora_2026-11-23_08:00")
    e.boton("cita_acepto")

    e.flujo.manejar_mensaje(CLIENTE, mensaje)

    assert e.cita()["paso"] == "dato:nombre"
    assert DATOS[0]["pregunta"] in e.texto.llamadas[-1][1]


def test_dato_se_sanea_a_una_linea_y_se_recorta(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")
    e.fila("cita_hora_2026-11-23_08:00")
    e.boton("cita_acepto")

    e.escribir("Ana\nPrueba    con\tespacios " + "x" * 200)

    valor = e.cita()["datos"]["nombre"]
    assert valor.startswith("Ana Prueba con espacios")
    assert len(valor) == flujo_cita.LIMITE_DATO and "\n" not in valor


# -- Salidas --


def test_cancelar_escrito_en_cualquier_paso(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")
    e.fila("cita_hora_2026-11-23_08:00")
    e.boton("cita_acepto")
    cita_id = e.cita()["id"]

    e.escribir("Cancelar")

    assert e.citas.obtener(cita_id)["estado"] == ESTADO_CANCELADA
    assert e.texto.llamadas[-1] == (CLIENTE, MENSAJE_CITA_CANCELADA)


def test_boton_cancelar_en_la_confirmacion(tmp_path):
    e = Escenario(tmp_path)
    e.hasta_confirmacion()

    e.boton("cita_cancelar")

    assert e.cita() is None
    assert e.texto.llamadas[-1] == (CLIENTE, MENSAJE_CITA_CANCELADA)


def test_asesor_cancela_deriva_y_avisa_al_dueno(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")

    e.escribir("asesor")

    assert e.cita() is None
    assert e.texto.llamadas[-1] == (CLIENTE, MENSAJE_DERIVACION)
    assert "mientras agendaba una cita" in e.con_wamid.llamadas[-1][1]


def test_30_minutos_sin_respuesta_cancela(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")
    e.ahora["valor"] += 30 * 60 + 1

    e.fila("cita_hora_2026-11-23_08:00")

    assert e.texto.llamadas[-1] == (CLIENTE, MENSAJE_CANCELADA_POR_INACTIVIDAD)
    assert e.cita() is None


def test_entrada_no_reconocida_reenvia_el_paso(tmp_path):
    e = Escenario(tmp_path)
    e.fila("cita_dia_2026-11-23")

    e.escribir("el que sea")

    assert e.texto.llamadas[-1][1] == MENSAJE_ENTRADA_NO_RECONOCIDA
    assert e.filas_ultima_lista()[0]["titulo"] == "8:00 a.m."


def test_botones_de_cita_sin_cita_en_construccion_se_ignoran(tmp_path):
    e = Escenario(tmp_path)

    e.boton("cita_confirmar")
    e.boton("cita_acepto")

    assert e.texto.llamadas == [] and e.botones.llamadas == [] and e.lista.llamadas == []
    assert e.cita() is None


def test_logs_sin_telefono_completo_ni_datos_de_la_cita(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    e = Escenario(tmp_path)
    e.hasta_confirmacion()

    e.boton("cita_confirmar")

    mensajes = "\n".join(r.getMessage() for r in caplog.records)
    assert "Cita #" in mensajes
    assert CLIENTE not in mensajes and DUENO not in mensajes
    assert "Ana Prueba" not in mensajes and "Toby" not in mensajes and "Vacunas" not in mensajes


# -- Vista del dueño, retención y formato --


def test_lista_de_proximas_citas_del_dueno_paginada_y_sin_telefono(tmp_path):
    e = Escenario(tmp_path, config=_config(dias_hacia_adelante=20, horario={"lunes": [["08:00", "14:00"]]}))
    assert flujo_cita.pagina_de_proximas_citas(e.citas, PERFIL, e.config, DOMINGO_NOCHE) is None
    for i in range(11):
        numero = f"5730000003{i:02d}"
        e.hasta_confirmacion(numero=numero, hora=f"{8 + i // 2:02d}:{'30' if i % 2 else '00'}")
        e.boton("cita_confirmar", numero=numero)

    primera = flujo_cita.pagina_de_proximas_citas(e.citas, PERFIL, e.config, DOMINGO_NOCHE)[0]["filas"]
    segunda = flujo_cita.pagina_de_proximas_citas(e.citas, PERFIL, e.config, DOMINGO_NOCHE, 2)[0]["filas"]

    assert len(primera) == 10 and primera[-1]["id"] == "citas_pagina_2"
    assert primera[0]["titulo"] == "Lun 23 nov 8:00 a.m."
    assert primera[0]["descripcion"].endswith("Nombre: Ana Prueba")
    assert len(segunda) == 2
    textos = str(primera) + str(segunda)
    assert "5730000003" not in textos


def test_detalle_para_el_dueno_incluye_datos_y_telefono(tmp_path):
    e = Escenario(tmp_path)
    e.hasta_confirmacion()
    cita_id = e.cita()["id"]
    e.boton("cita_confirmar")

    detalle = flujo_cita.detalle_cita_para_dueno(e.citas.obtener(cita_id), e.config)

    assert f"Cita #{cita_id}" in detalle and CLIENTE in detalle and "Motivo: Vacunas" in detalle
    e.citas.cancelar(cita_id, DOMINGO_NOCHE)
    assert flujo_cita.detalle_cita_para_dueno(e.citas.obtener(cita_id), e.config) == "Esa cita ya no está agendada."
    assert flujo_cita.detalle_cita_para_dueno(None, e.config) == "Esa cita ya no está agendada."


@pytest.mark.parametrize(
    "id_fila, esperado",
    [("ver_cita_12", ("ver", 12)), ("citas_pagina_2", ("pagina", 2)), ("ver_cita_x", None), ("ver_pedido_1", None)],
)
def test_interpretar_fila_del_dueno(id_fila, esperado):
    assert flujo_cita.interpretar_fila_dueno(id_fila) == esperado


def test_aplicar_retencion_usa_los_dias_del_perfil(tmp_path):
    e = Escenario(tmp_path, config=_config(retencion_dias=10))
    e.hasta_confirmacion()
    cita_id = e.cita()["id"]
    e.boton("cita_confirmar")

    assert flujo_cita.aplicar_retencion(e.citas, PERFIL, e.config, _reloj(2026, 12, 2)) == 0  # 9 días después
    assert flujo_cita.aplicar_retencion(e.citas, PERFIL, e.config, _reloj(2026, 12, 4)) == 1  # 11 días después
    assert e.citas.obtener(cita_id)["datos"] == {}


@pytest.mark.parametrize(
    "inicio, esperado",
    [("2026-11-23 08:00", "8:00 a.m."), ("2026-11-23 12:00", "12:00 p.m."), ("2026-11-23 00:30", "12:30 a.m."), ("2026-11-23 14:30", "2:30 p.m.")],
)
def test_hora_legible(inicio, esperado):
    assert flujo_cita.hora_legible(inicio) == esperado


def test_dia_corto_y_largo():
    assert flujo_cita.dia_corto(date(2026, 11, 28)) == "Sáb 28 nov"
    assert flujo_cita.dia_largo(date(2026, 11, 25)) == "miércoles 25 de noviembre"
