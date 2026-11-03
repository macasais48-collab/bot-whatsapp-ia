import json
import logging

import requests

from media_cache import SEGUNDOS_VENCIMIENTO_MEDIA_ID, obtener_media_id

AHORA = 1_800_000_000


def _reloj_fijo():
    return AHORA


def _preparar_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_TOKEN", "token_secreto_de_prueba_no_debe_aparecer")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("GRAPH_API_VERSION", "v26.0")
    ruta_cache = tmp_path / "media_id_cache.json"
    monkeypatch.setenv("RUTA_CACHE_MEDIA", str(ruta_cache))
    return ruta_cache


def _escribir_imagen(tmp_path, nombre="pan.jpg"):
    ruta = tmp_path / nombre
    ruta.write_bytes(b"\xff\xd8\xff\xe0contenido-de-prueba")
    return ruta


class RespuestaFalsa:
    def __init__(self, status_code, cuerpo_json):
        self.status_code = status_code
        self._cuerpo_json = cuerpo_json

    def json(self):
        return self._cuerpo_json


def test_sube_la_imagen_si_no_hay_nada_en_cache(monkeypatch, tmp_path):
    ruta_cache = _preparar_entorno(monkeypatch, tmp_path)
    ruta_archivo = _escribir_imagen(tmp_path)

    llamadas = []

    def post_falso(url, headers, data, files, timeout):
        llamadas.append(url)
        return RespuestaFalsaOk()

    class RespuestaFalsaOk:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "media_nuevo_123"}

    monkeypatch.setattr("media_cache.requests.post", post_falso)

    media_id = obtener_media_id("pan", ruta_archivo, reloj=_reloj_fijo)

    assert media_id == "media_nuevo_123"
    assert len(llamadas) == 1
    cache_guardado = json.loads(ruta_cache.read_text(encoding="utf-8"))
    assert cache_guardado["pan"]["media_id"] == "media_nuevo_123"
    assert cache_guardado["pan"]["subido_en"] == AHORA


def test_usa_el_cache_si_el_media_id_sigue_vigente(monkeypatch, tmp_path):
    ruta_cache = _preparar_entorno(monkeypatch, tmp_path)
    ruta_archivo = _escribir_imagen(tmp_path)
    ruta_cache.write_text(
        json.dumps({"pan": {"media_id": "media_vigente", "subido_en": AHORA - 10}}), encoding="utf-8"
    )

    def post_falso(*args, **kwargs):
        raise AssertionError("no debería subirse de nuevo si el caché sigue vigente")

    monkeypatch.setattr("media_cache.requests.post", post_falso)

    media_id = obtener_media_id("pan", ruta_archivo, reloj=_reloj_fijo)

    assert media_id == "media_vigente"


def test_resube_si_el_media_id_tiene_mas_de_25_dias(monkeypatch, tmp_path):
    ruta_cache = _preparar_entorno(monkeypatch, tmp_path)
    ruta_archivo = _escribir_imagen(tmp_path)
    subido_hace_mucho = AHORA - SEGUNDOS_VENCIMIENTO_MEDIA_ID - 1
    ruta_cache.write_text(
        json.dumps({"pan": {"media_id": "media_vencido", "subido_en": subido_hace_mucho}}), encoding="utf-8"
    )

    class RespuestaFalsaOk:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "media_renovado"}

    def post_falso(*args, **kwargs):
        return RespuestaFalsaOk()

    monkeypatch.setattr("media_cache.requests.post", post_falso)

    media_id = obtener_media_id("pan", ruta_archivo, reloj=_reloj_fijo)

    assert media_id == "media_renovado"
    cache_guardado = json.loads(ruta_cache.read_text(encoding="utf-8"))
    assert cache_guardado["pan"]["media_id"] == "media_renovado"
    assert cache_guardado["pan"]["subido_en"] == AHORA


def test_subida_fallida_se_registra_sin_lanzar_y_sin_exponer_el_token(monkeypatch, tmp_path, caplog):
    _preparar_entorno(monkeypatch, tmp_path)
    ruta_archivo = _escribir_imagen(tmp_path)

    respuesta_falsa = RespuestaFalsa(
        400, {"error": {"message": "Unsupported media type", "code": 131009, "error_subcode": 2494007}}
    )

    def post_falso(*args, **kwargs):
        raise requests.exceptions.HTTPError(response=respuesta_falsa)

    monkeypatch.setattr("media_cache.requests.post", post_falso)
    caplog.set_level(logging.ERROR, logger="media_cache")

    media_id = obtener_media_id("pan", ruta_archivo, reloj=_reloj_fijo)

    assert media_id is None
    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert "131009" in mensajes
    assert "token_secreto_de_prueba_no_debe_aparecer" not in mensajes
