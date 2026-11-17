from datetime import date, datetime

import pytest

import agenda
from agenda import (
    ZONA_BOGOTA,
    dias_disponibles,
    es_festivo,
    franjas_del_dia,
    horas_libres,
    inicio_disponible,
    rango_de_consulta,
    validar_config_citas,
)

# Semana de referencia sin festivos: lunes 23 a domingo 29 de noviembre de 2026.
LUNES = date(2026, 11, 23)
DOMINGO = date(2026, 11, 29)
SABADO = date(2026, 11, 28)


def _reloj(anio, mes, dia, hora=7, minuto=0):
    return datetime(anio, mes, dia, hora, minuto, tzinfo=ZONA_BOGOTA).timestamp()


def _config(**cambios):
    base = {
        "duracion_minutos": 30,
        "horario": {
            dia: [["08:00", "12:00"], ["14:00", "18:00"]]
            for dia in ("lunes", "martes", "miercoles", "jueves", "viernes")
        }
        | {"sabado": [["09:00", "12:00"]]},
        "datos": [{"clave": "nombre", "pregunta": "¿A nombre de quién?", "etiqueta": "Nombre"}],
    }
    base.update(cambios)
    return validar_config_citas(base, "recursos_prueba.json")


# -- Validación --


def test_config_minima_toma_los_valores_por_defecto():
    config = _config()

    assert config["cupos_por_horario"] == 1
    assert config["anticipacion_minima_minutos"] == 60
    assert config["dias_hacia_adelante"] == 14
    assert config["max_citas_por_cliente"] == 3
    assert config["retencion_dias"] == 30
    assert config["festivos"] == "cerrado"
    assert config["dias_bloqueados"] == frozenset()
    assert config["telefono_negocio"] is None
    assert config["horario"][0] == [(480, 720), (840, 1080)]  # lunes en minutos
    assert 6 not in config["horario"]  # domingo no se atiende


@pytest.mark.parametrize(
    "cambios, fragmento",
    [
        ({"duracion_minutos": 0}, "duracion_minutos"),
        ({"duracion_minutos": True}, "duracion_minutos"),
        ({"cupos_por_horario": 0}, "cupos_por_horario"),
        ({"dias_hacia_adelante": 61}, "dias_hacia_adelante"),
        ({"anticipacion_minima_minutos": -1}, "anticipacion_minima_minutos"),
        ({"max_citas_por_cliente": 0}, "max_citas_por_cliente"),
        ({"retencion_dias": 0}, "retencion_dias"),
        ({"festivos": "a veces"}, "festivos"),
        ({"dias_bloqueados": ["2026-13-01"]}, "dias_bloqueados"),
        ({"dias_bloqueados": "2026-12-24"}, "dias_bloqueados"),
        ({"horario": {}}, "horario"),
        ({"horario": {"Lunes": [["08:00", "12:00"]]}}, "Lunes"),
        ({"horario": {"lunes": [["8:00", "12:00"]]}}, "HH:MM"),
        ({"horario": {"lunes": [["08:00", "24:00"]]}}, "HH:MM"),
        ({"horario": {"lunes": [["12:00", "08:00"]]}}, "anterior"),
        ({"horario": {"lunes": [["08:00", "12:00"], ["11:00", "13:00"]]}}, "se cruzan"),
        ({"horario": {"lunes": ["08:00", "12:00"]}}, "lunes"),
        ({"datos": []}, "datos"),
        ({"datos": [{"clave": f"d{i}", "pregunta": "p", "etiqueta": "e"} for i in range(6)]}, "datos"),
        ({"datos": [{"clave": "Nombre", "pregunta": "p", "etiqueta": "e"}]}, "clave"),
        ({"datos": [{"clave": "a", "pregunta": "p", "etiqueta": "e"}] * 2}, "repite"),
        ({"datos": [{"clave": "a", "pregunta": "", "etiqueta": "e"}]}, "pregunta"),
        ({"datos": [{"clave": "a", "pregunta": "p", "etiqueta": "x" * 21}]}, "etiqueta"),
        ({"telefono_negocio": "llamar"}, "telefono_negocio"),
        ({"clave_inventada": 1}, "no reconocidas"),
    ],
)
def test_config_invalida_falla_con_mensaje_claro(cambios, fragmento):
    with pytest.raises(ValueError, match=fragmento):
        _config(**cambios)


@pytest.mark.parametrize("obligatoria", ["duracion_minutos", "horario", "datos"])
def test_campos_obligatorios(obligatoria):
    base = {
        "duracion_minutos": 30,
        "horario": {"lunes": [["08:00", "12:00"]]},
        "datos": [{"clave": "nombre", "pregunta": "p", "etiqueta": "Nombre"}],
    }
    del base[obligatoria]

    with pytest.raises(ValueError, match=obligatoria):
        validar_config_citas(base, "recursos_prueba.json")


# -- Franjas del día --


def test_franjas_de_un_dia_con_dos_franjas():
    franjas = franjas_del_dia(_config(), LUNES)

    assert len(franjas) == 16
    assert franjas[0] == "2026-11-23 08:00"
    assert franjas[7] == "2026-11-23 11:30"
    assert franjas[8] == "2026-11-23 14:00"
    assert franjas[-1] == "2026-11-23 17:30"


def test_solo_se_ofrece_una_hora_si_la_cita_completa_cabe_en_la_franja():
    franjas = franjas_del_dia(_config(duracion_minutos=45), LUNES)

    manana = [f[-5:] for f in franjas if f[-5:] < "13:00"]
    assert manana == ["08:00", "08:45", "09:30", "10:15", "11:00"]  # 11:45 + 45 min pasaría de las 12:00


def test_dia_sin_horario_no_tiene_franjas():
    assert franjas_del_dia(_config(), DOMINGO) == []


def test_festivo_cerrado_por_defecto_y_abierto_si_se_configura():
    festivo = date(2026, 12, 8)  # Inmaculada Concepción, martes
    assert es_festivo(festivo)

    assert franjas_del_dia(_config(), festivo) == []
    assert len(franjas_del_dia(_config(festivos="abierto"), festivo)) == 16


def test_festivo_trasladado_tambien_cuenta():
    # 11 de noviembre de 2026 (miércoles) se traslada al lunes 16 (Ley Emiliani).
    assert es_festivo(date(2026, 11, 16))
    assert not es_festivo(date(2026, 11, 11))


def test_dia_bloqueado_no_tiene_franjas():
    assert franjas_del_dia(_config(dias_bloqueados=["2026-11-23"]), LUNES) == []


# -- Horas libres --


def test_hoy_no_ofrece_horas_pasadas_ni_antes_de_la_anticipacion():
    ahora = _reloj(2026, 11, 23, 10, 10)  # primer inicio permitido: 11:10

    libres = horas_libres(_config(), LUNES, ahora, {})

    assert libres[0] == "2026-11-23 11:30"
    assert len(libres) == 9  # 11:30 + las 8 de la tarde


def test_anticipacion_justo_en_el_limite_incluye_esa_hora():
    ahora = _reloj(2026, 11, 23, 10, 0)  # + 60 min = 11:00 exacto

    libres = horas_libres(_config(), LUNES, ahora, {})

    assert libres[:2] == ["2026-11-23 11:00", "2026-11-23 11:30"]


def test_anticipacion_cero_ofrece_la_hora_actual_exacta():
    ahora = _reloj(2026, 11, 23, 8, 0)

    assert horas_libres(_config(anticipacion_minima_minutos=0), LUNES, ahora, {})[0] == "2026-11-23 08:00"


def test_horario_ocupado_no_se_ofrece_con_un_cupo():
    ahora = _reloj(2026, 11, 22)

    libres = horas_libres(_config(), LUNES, ahora, {"2026-11-23 08:00": 1})

    assert "2026-11-23 08:00" not in libres
    assert "2026-11-23 08:30" in libres


def test_con_varios_cupos_se_ofrece_hasta_llenarlos():
    ahora = _reloj(2026, 11, 22)
    config = _config(cupos_por_horario=2)

    assert "2026-11-23 08:00" in horas_libres(config, LUNES, ahora, {"2026-11-23 08:00": 1})
    assert "2026-11-23 08:00" not in horas_libres(config, LUNES, ahora, {"2026-11-23 08:00": 2})


def test_dia_pasado_no_ofrece_nada():
    ahora = _reloj(2026, 11, 24)

    assert horas_libres(_config(), LUNES, ahora, {}) == []


# -- Días disponibles y ventana --


def test_ventana_incluye_el_ultimo_dia_y_excluye_el_siguiente():
    ahora = _reloj(2026, 11, 23)  # lunes
    config = _config(dias_hacia_adelante=7)

    dias = dias_disponibles(config, ahora, {})

    assert dias[-1] == date(2026, 11, 30)  # lunes siguiente, día 7: incluido
    assert date(2026, 12, 1) not in dias  # día 8: fuera
    assert horas_libres(config, date(2026, 12, 1), ahora, {}) == []


def test_dias_disponibles_omite_dias_sin_horario_y_dias_llenos():
    ahora = _reloj(2026, 11, 22, 20, 0)  # domingo en la noche
    config = _config(dias_hacia_adelante=6)
    ocupacion_martes_lleno = {inicio: 1 for inicio in franjas_del_dia(config, date(2026, 11, 24))}

    dias = dias_disponibles(config, ahora, ocupacion_martes_lleno)

    assert date(2026, 11, 22) not in dias  # domingo, sin horario
    assert date(2026, 11, 24) not in dias  # martes lleno
    assert dias == [date(2026, 11, 23), date(2026, 11, 25), date(2026, 11, 26), date(2026, 11, 27), SABADO]


def test_hoy_no_aparece_despues_de_la_ultima_hora():
    ahora = _reloj(2026, 11, 23, 17, 10)  # + 60 min ya pasa la última (17:30)

    assert LUNES not in dias_disponibles(_config(dias_hacia_adelante=2), ahora, {})


def test_cambio_de_anio_y_festivo_de_anio_nuevo():
    ahora = _reloj(2026, 12, 30)
    config = _config(dias_hacia_adelante=3)

    dias = dias_disponibles(config, ahora, {})

    assert date(2026, 12, 31) in dias
    assert date(2027, 1, 1) not in dias  # festivo
    assert date(2027, 1, 2) in dias  # sábado
    assert franjas_del_dia(config, date(2027, 1, 2))[0] == "2027-01-02 09:00"


def test_rango_de_consulta_cubre_toda_la_ventana():
    assert rango_de_consulta(_config(dias_hacia_adelante=7), _reloj(2026, 11, 23, 15, 0)) == (
        "2026-11-23 00:00",
        "2026-11-30 23:59",
    )


# -- Inicio disponible (filas de listas viejas) --


@pytest.mark.parametrize(
    "inicio, ocupacion, esperado",
    [
        ("2026-11-23 09:00", {}, True),
        ("2026-11-23 09:00", {"2026-11-23 09:00": 1}, False),  # ocupado
        ("2026-11-23 08:15", {}, False),  # fuera de la rejilla
        ("2026-11-23 12:30", {}, False),  # entre franjas
        ("2026-11-22 09:00", {}, False),  # domingo
        ("2026-11-20 09:00", {}, False),  # pasado
        ("hoy a las 9", {}, False),  # malformado
        (None, {}, False),
    ],
)
def test_inicio_disponible_recalcula_todo(inicio, ocupacion, esperado):
    ahora = _reloj(2026, 11, 22, 20, 0)

    assert inicio_disponible(_config(), inicio, ahora, ocupacion) is esperado


def test_el_modulo_no_depende_de_la_base_ni_de_la_red():
    import sys

    assert "basedatos" not in agenda.__dict__
    assert "requests" not in agenda.__dict__
    assert "agenda" in sys.modules
