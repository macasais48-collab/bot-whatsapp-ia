import logging

import pytest
import requests

from red_meta import INTENTOS_MAXIMOS, peticion_con_reintentos


class _RespuestaFalsa:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def test_reintenta_ante_error_de_conexion_y_termina_en_exito(monkeypatch, caplog):
    llamadas = {"n": 0}

    def hacer_peticion():
        llamadas["n"] += 1
        if llamadas["n"] < 2:
            raise requests.exceptions.ConnectionError("sin red")
        return "ok"

    monkeypatch.setattr("red_meta.time.sleep", lambda segundos: None)
    caplog.set_level(logging.WARNING, logger="red_meta")

    resultado = peticion_con_reintentos(hacer_peticion)

    assert resultado == "ok"
    assert llamadas["n"] == 2
    assert any("reintento" in r.getMessage().lower() for r in caplog.records)


def test_reintenta_ante_429_y_respeta_retry_after(monkeypatch):
    llamadas = {"n": 0}
    esperas = []
    monkeypatch.setattr("red_meta.time.sleep", lambda segundos: esperas.append(segundos))

    def hacer_peticion():
        llamadas["n"] += 1
        if llamadas["n"] < 2:
            raise requests.exceptions.HTTPError(response=_RespuestaFalsa(429, {"Retry-After": "5"}))
        return "ok"

    resultado = peticion_con_reintentos(hacer_peticion)

    assert resultado == "ok"
    assert esperas[0] == 5.0  # Retry-After (5s) pesa más que la espera por defecto (1s)


def test_no_reintenta_ante_timeout_para_no_duplicar_el_mensaje():
    llamadas = {"n": 0}

    def hacer_peticion():
        llamadas["n"] += 1
        raise requests.exceptions.Timeout("tardó demasiado")

    with pytest.raises(requests.exceptions.Timeout):
        peticion_con_reintentos(hacer_peticion)

    assert llamadas["n"] == 1


def test_no_reintenta_ante_otro_codigo_http():
    llamadas = {"n": 0}

    def hacer_peticion():
        llamadas["n"] += 1
        raise requests.exceptions.HTTPError(response=_RespuestaFalsa(400))

    with pytest.raises(requests.exceptions.HTTPError):
        peticion_con_reintentos(hacer_peticion)

    assert llamadas["n"] == 1


def test_agota_los_intentos_y_relanza(monkeypatch):
    llamadas = {"n": 0}
    monkeypatch.setattr("red_meta.time.sleep", lambda segundos: None)

    def hacer_peticion():
        llamadas["n"] += 1
        raise requests.exceptions.ConnectionError("sin red")

    with pytest.raises(requests.exceptions.ConnectionError):
        peticion_con_reintentos(hacer_peticion)

    assert llamadas["n"] == INTENTOS_MAXIMOS
