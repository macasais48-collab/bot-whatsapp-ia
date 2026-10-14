import logging

import requests

from whatsapp import enviar_texto


class RespuestaFalsa:
    def __init__(self, status_code, cuerpo_json):
        self.status_code = status_code
        self._cuerpo_json = cuerpo_json

    def json(self):
        return self._cuerpo_json


def test_enviar_texto_registra_el_detalle_del_error_de_meta_sin_el_token(monkeypatch, caplog):
    monkeypatch.setenv("WHATSAPP_TOKEN", "token_secreto_de_prueba_no_debe_aparecer")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("GRAPH_API_VERSION", "v26.0")

    respuesta_falsa = RespuestaFalsa(
        400,
        {
            "error": {
                "message": "Recipient phone number not in allowed list",
                "type": "OAuthException",
                "code": 131030,
                "error_subcode": 2494055,
            }
        },
    )

    def post_falso(*args, **kwargs):
        raise requests.exceptions.HTTPError(response=respuesta_falsa)

    monkeypatch.setattr("whatsapp.requests.post", post_falso)
    caplog.set_level(logging.ERROR, logger="whatsapp")

    resultado = enviar_texto("573000000000", "hola")

    assert resultado is False
    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert "131030" in mensajes
    assert "2494055" in mensajes
    assert "Recipient phone number not in allowed list" in mensajes
    assert "token_secreto_de_prueba_no_debe_aparecer" not in mensajes


def test_enviar_texto_no_falla_si_la_respuesta_de_error_no_trae_json(monkeypatch, caplog):
    monkeypatch.setenv("WHATSAPP_TOKEN", "token_secreto_de_prueba_no_debe_aparecer")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("GRAPH_API_VERSION", "v26.0")

    class RespuestaSinJson(RespuestaFalsa):
        def json(self):
            raise ValueError("no es JSON")

    respuesta_falsa = RespuestaSinJson(500, {})

    def post_falso(*args, **kwargs):
        raise requests.exceptions.HTTPError(response=respuesta_falsa)

    monkeypatch.setattr("whatsapp.requests.post", post_falso)
    caplog.set_level(logging.ERROR, logger="whatsapp")

    resultado = enviar_texto("573000000000", "hola")

    assert resultado is False
    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert "código=500" in mensajes
