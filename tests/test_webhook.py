import hashlib
import hmac
import json
import logging

import pytest

from almacenamiento import HistorialSQLite
from cerebro import Cerebro
from historial import HistorialMemoria
from llm.base import ProveedorIA
from webhook import (
    MENSAJE_DERIVACION_POR_DEFECTO,
    MENSAJE_SOLO_TEXTO,
    PERFIL_NEGOCIO_POR_DEFECTO,
    PERFILES_NEGOCIO,
    UMBRAL_MENSAJE_VIEJO_SEGUNDOS,
    _extraer_mensaje_derivacion,
    _resolver_ruta_negocio,
    crear_app,
)

APP_SECRET = "secreto_de_prueba"
VERIFY_TOKEN = "token_de_prueba"

# Todos los payloads de prueba traen "timestamp": "1700000000" (ver _payload_mensaje).
# El reloj de prueba se fija justo 10 segundos después, para que ese timestamp
# siempre cuente como "reciente" salvo que una prueba quiera lo contrario a propósito.
RELOJ_PRUEBA_SEGUNDOS = 1700000000 + 10


class FakeProveedor(ProveedorIA):
    def __init__(self, salida):
        self.salida = salida

    def responder(self, sistema, mensajes):
        return self.salida


class EnviosFalsos:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, texto):
        self.llamadas.append((numero, texto))
        return True


class EnviosUbicacionFalsos:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, latitud, longitud, nombre, direccion):
        self.llamadas.append((numero, latitud, longitud, nombre, direccion))
        return True


class EnviosCtaUrlFalsos:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, texto_cuerpo, texto_boton, url):
        self.llamadas.append((numero, texto_cuerpo, texto_boton, url))
        return True


class EnviosImagenFalsos:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, media_id, caption=None):
        self.llamadas.append((numero, media_id, caption))
        return True


class ObtencionMediaIdFalsa:
    """Simula media_cache.obtener_media_id sin red real: devuelve un media id fijo
    por clave, o None si la clave está en `claves_que_fallan` (subida fallida)."""

    def __init__(self, media_id="media_de_prueba_123", claves_que_fallan=()):
        self.media_id = media_id
        self.claves_que_fallan = set(claves_que_fallan)
        self.llamadas = []

    def __call__(self, clave, ruta_archivo):
        self.llamadas.append((clave, ruta_archivo))
        if clave in self.claves_que_fallan:
            return None
        return self.media_id


def _firmar(cuerpo: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()


def _post_con_firma(cliente, payload, firma=None):
    cuerpo = json.dumps(payload).encode("utf-8")
    encabezados = {"Content-Type": "application/json"}
    if firma != "omitir":
        encabezados["X-Hub-Signature-256"] = firma if firma else _firmar(cuerpo)
    return cliente.post("/webhook", data=cuerpo, headers=encabezados)


def _payload_mensaje(id_mensaje, numero, mensaje_extra):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "999"},
                            "messages": [
                                {
                                    "from": numero,
                                    "id": id_mensaje,
                                    "timestamp": "1700000000",
                                    **mensaje_extra,
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _payload_mensaje_texto(id_mensaje, numero, texto):
    return _payload_mensaje(id_mensaje, numero, {"type": "text", "text": {"body": texto}})


def _payload_mensaje_imagen(id_mensaje, numero):
    return _payload_mensaje(id_mensaje, numero, {"type": "image", "image": {"id": "abc123"}})


def _payload_estado(id_mensaje, numero):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "999"},
                            "statuses": [
                                {
                                    "id": id_mensaje,
                                    "status": "delivered",
                                    "timestamp": "1700000000",
                                    "recipient_id": numero,
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture
def envios():
    return EnviosFalsos()


@pytest.fixture
def envios_ubicacion():
    return EnviosUbicacionFalsos()


@pytest.fixture
def envios_cta_url():
    return EnviosCtaUrlFalsos()


@pytest.fixture
def envios_imagen():
    return EnviosImagenFalsos()


@pytest.fixture
def obtencion_media_id():
    return ObtencionMediaIdFalsa()


@pytest.fixture
def fabrica_cliente(tmp_path, monkeypatch, envios, envios_ubicacion, envios_cta_url, envios_imagen, obtencion_media_id):
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", VERIFY_TOKEN)

    contador = {"n": 0}

    def _crear(
        salida_ia='{"respuesta": "ok", "derivar": false}',
        reloj=None,
        ruta_recursos=None,
        obtener_media_id_fn=None,
    ):
        contador["n"] += 1
        fake_proveedor = FakeProveedor(salida_ia)
        historial_dedup = HistorialSQLite(tmp_path / f"prueba_{contador['n']}.db")
        cerebro = Cerebro(fake_proveedor, HistorialMemoria(), ruta_recursos=ruta_recursos)
        app = crear_app(
            cerebro=cerebro,
            historial_dedup=historial_dedup,
            enviar_texto_fn=envios,
            enviar_ubicacion_fn=envios_ubicacion,
            enviar_cta_url_fn=envios_cta_url,
            enviar_imagen_fn=envios_imagen,
            obtener_media_id_fn=obtener_media_id_fn or obtencion_media_id,
            reloj=reloj or (lambda: RELOJ_PRUEBA_SEGUNDOS),
        )
        app.testing = True
        return app.test_client()

    return _crear


def test_salud_responde_200_ok_sin_exponer_nada(fabrica_cliente):
    cliente = fabrica_cliente()

    respuesta = cliente.get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.get_data(as_text=True) == "ok"


def test_get_con_token_correcto_devuelve_el_challenge(fabrica_cliente):
    cliente = fabrica_cliente()

    respuesta = cliente.get(
        "/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.get_data(as_text=True) == "1158201444"


def test_get_con_token_incorrecto_devuelve_403(fabrica_cliente):
    cliente = fabrica_cliente()

    respuesta = cliente.get(
        "/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "token_equivocado",
            "hub.challenge": "1158201444",
        },
    )

    assert respuesta.status_code == 403


def test_post_con_firma_valida_se_procesa_y_responde(fabrica_cliente, envios):
    cliente = fabrica_cliente(json.dumps({"respuesta": "Abrimos a las 6am", "derivar": False}))
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "¿A qué hora abren?")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", "Abrimos a las 6am")]


def test_post_con_firma_invalida_devuelve_403_y_no_procesa(fabrica_cliente, envios):
    cliente = fabrica_cliente()
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "hola")

    respuesta = _post_con_firma(cliente, payload, firma="sha256=firma_invalida_de_prueba")

    assert respuesta.status_code == 403
    assert envios.llamadas == []


def test_post_sin_firma_devuelve_403_y_no_procesa(fabrica_cliente, envios):
    cliente = fabrica_cliente()
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "hola")

    respuesta = _post_con_firma(cliente, payload, firma="omitir")

    assert respuesta.status_code == 403
    assert envios.llamadas == []


def test_post_notificacion_de_estado_devuelve_200_sin_respuesta(fabrica_cliente, envios):
    cliente = fabrica_cliente()
    payload = _payload_estado("wamid.1", "573001112233")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == []


def test_post_mensaje_duplicado_se_procesa_una_sola_vez(fabrica_cliente, envios):
    cliente = fabrica_cliente()
    payload = _payload_mensaje_texto("wamid.repetido", "573001112233", "hola")

    _post_con_firma(cliente, payload)
    respuesta_repetida = _post_con_firma(cliente, payload)

    assert respuesta_repetida.status_code == 200
    assert len(envios.llamadas) == 1


def test_post_mensaje_no_texto_responde_amablemente(fabrica_cliente, envios):
    cliente = fabrica_cliente()
    payload = _payload_mensaje_imagen("wamid.1", "573001112233")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", MENSAJE_SOLO_TEXTO)]


def test_post_con_derivar_true_envia_mensaje_de_derivacion(fabrica_cliente, envios):
    cliente = fabrica_cliente(json.dumps({"respuesta": "no sé", "derivar": True}))
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "algo muy raro")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", MENSAJE_DERIVACION_POR_DEFECTO)]


def test_get_no_registra_el_token_ni_el_challenge_en_los_logs(fabrica_cliente, caplog):
    cliente = fabrica_cliente()
    caplog.set_level(logging.INFO, logger="webhook")
    token_secreto = "token_secreto_de_prueba_xyz"
    challenge_secreto = "challenge_secreto_987"

    cliente.get(
        "/webhook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": token_secreto,
            "hub.challenge": challenge_secreto,
        },
    )

    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert token_secreto not in mensajes
    assert challenge_secreto not in mensajes
    assert "GET" in mensajes
    assert "/webhook" in mensajes


def test_post_con_firma_ausente_registra_diagnostico_sin_exponer_nada(fabrica_cliente, caplog):
    cliente = fabrica_cliente()
    caplog.set_level(logging.WARNING, logger="webhook")
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "hola")

    _post_con_firma(cliente, payload, firma="omitir")

    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert "ausente" in mensajes.lower()


def test_post_con_firma_invalida_registra_diagnostico_sin_exponer_nada(fabrica_cliente, caplog):
    cliente = fabrica_cliente()
    caplog.set_level(logging.WARNING, logger="webhook")
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "hola")
    firma_falsa = "sha256=firma_invalida_de_prueba"

    _post_con_firma(cliente, payload, firma=firma_falsa)

    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert "no coincide" in mensajes.lower()
    assert firma_falsa not in mensajes


def test_resolver_ruta_negocio_usa_panaderia_si_no_esta_definida(monkeypatch):
    monkeypatch.delenv("PERFIL_NEGOCIO", raising=False)

    assert _resolver_ruta_negocio() == PERFILES_NEGOCIO[PERFIL_NEGOCIO_POR_DEFECTO]


def test_resolver_ruta_negocio_carga_el_perfil_de_camilo(monkeypatch):
    monkeypatch.setenv("PERFIL_NEGOCIO", "camilo")

    assert _resolver_ruta_negocio() == PERFILES_NEGOCIO["camilo"]


def test_resolver_ruta_negocio_falla_con_valor_desconocido(monkeypatch):
    monkeypatch.setenv("PERFIL_NEGOCIO", "no-existe")

    with pytest.raises(ValueError) as info:
        _resolver_ruta_negocio()

    assert "PERFIL_NEGOCIO no es válido" in str(info.value)
    assert "panaderia" in str(info.value)
    assert "camilo" in str(info.value)


def test_extraer_mensaje_derivacion_usa_el_default_si_el_perfil_no_tiene_seccion():
    assert _extraer_mensaje_derivacion(PERFILES_NEGOCIO["panaderia"]) == MENSAJE_DERIVACION_POR_DEFECTO


def test_extraer_mensaje_derivacion_lee_la_seccion_del_perfil_camilo():
    mensaje = _extraer_mensaje_derivacion(PERFILES_NEGOCIO["camilo"])

    assert mensaje == (
        "Le comunico con Camilo, que le responderá en su horario de atención "
        "(lunes a sábado, 8:00 a.m. a 6:00 p.m.)."
    )
    assert mensaje != MENSAJE_DERIVACION_POR_DEFECTO


def test_mensaje_viejo_se_ignora_sin_responder(fabrica_cliente, envios, caplog):
    caplog.set_level(logging.INFO, logger="webhook")
    cliente = fabrica_cliente()
    timestamp_viejo = str(RELOJ_PRUEBA_SEGUNDOS - UMBRAL_MENSAJE_VIEJO_SEGUNDOS - 100)
    payload = _payload_mensaje("wamid.viejo", "573001112233", {"type": "text", "text": {"body": "hola"}})
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = timestamp_viejo

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == []
    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert "antiguo" in mensajes.lower()


def test_mensaje_reciente_se_procesa_normalmente(fabrica_cliente, envios):
    cliente = fabrica_cliente(json.dumps({"respuesta": "Abrimos a las 6am", "derivar": False}))
    timestamp_reciente = str(RELOJ_PRUEBA_SEGUNDOS - 30)
    payload = _payload_mensaje_texto("wamid.reciente", "573001112233", "¿a qué hora abren?")
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = timestamp_reciente

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", "Abrimos a las 6am")]


RECURSOS_DE_PRUEBA_WEBHOOK = {
    "ubicacion": {
        "latitud": 4.73,
        "longitud": -74.26,
        "nombre": "Negocio de ejemplo",
        "direccion": "Calle falsa 123",
    },
    "enlaces": {
        "mapa": {
            "url": "https://maps.google.com/?q=4.73,-74.26",
            "texto_boton": "Ver en el mapa",
            "descripcion": "Así puedes ver nuestra ubicación.",
        }
    },
}


def _escribir_recursos_webhook(tmp_path, datos):
    ruta = tmp_path / "recursos_webhook.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def test_adjunto_de_ubicacion_valido_se_envia_despues_del_texto(fabrica_cliente, envios, envios_ubicacion, tmp_path):
    ruta_recursos = _escribir_recursos_webhook(tmp_path, RECURSOS_DE_PRUEBA_WEBHOOK)
    cliente = fabrica_cliente(
        json.dumps({"respuesta": "Quedamos aquí", "derivar": False, "adjuntos": [{"tipo": "ubicacion"}]}),
        ruta_recursos=ruta_recursos,
    )
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "¿dónde quedan?")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", "Quedamos aquí")]
    assert envios_ubicacion.llamadas == [
        ("573001112233", 4.73, -74.26, "Negocio de ejemplo", "Calle falsa 123")
    ]


def test_adjunto_de_enlace_valido_se_envia_despues_del_texto(fabrica_cliente, envios, envios_cta_url, tmp_path):
    ruta_recursos = _escribir_recursos_webhook(tmp_path, RECURSOS_DE_PRUEBA_WEBHOOK)
    cliente = fabrica_cliente(
        json.dumps(
            {"respuesta": "Aquí tienes", "derivar": False, "adjuntos": [{"tipo": "enlace", "clave": "mapa"}]}
        ),
        ruta_recursos=ruta_recursos,
    )
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "¿tienen mapa?")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", "Aquí tienes")]
    assert envios_cta_url.llamadas == [
        (
            "573001112233",
            "Así puedes ver nuestra ubicación.",
            "Ver en el mapa",
            "https://maps.google.com/?q=4.73,-74.26",
        )
    ]


def test_al_derivar_no_se_envia_ningun_adjunto_aunque_la_ia_los_pida(
    fabrica_cliente, envios, envios_ubicacion, envios_cta_url, tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="webhook")
    ruta_recursos = _escribir_recursos_webhook(tmp_path, RECURSOS_DE_PRUEBA_WEBHOOK)
    cliente = fabrica_cliente(
        json.dumps(
            {
                "respuesta": "no sé",
                "derivar": True,
                "adjuntos": [{"tipo": "ubicacion"}, {"tipo": "enlace", "clave": "mapa"}],
            }
        ),
        ruta_recursos=ruta_recursos,
    )
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "algo muy raro")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    # Al derivar se envía el mensaje fijo de derivación, nunca el texto de la IA
    # ni los adjuntos que haya pedido.
    assert envios.llamadas == [("573001112233", MENSAJE_DERIVACION_POR_DEFECTO)]
    assert envios_ubicacion.llamadas == []
    assert envios_cta_url.llamadas == []
    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert "2 adjunto" in mensajes


def test_clave_de_adjunto_inventada_por_la_ia_nunca_se_envia(
    fabrica_cliente, envios, envios_ubicacion, envios_cta_url, tmp_path
):
    ruta_recursos = _escribir_recursos_webhook(tmp_path, RECURSOS_DE_PRUEBA_WEBHOOK)
    cliente = fabrica_cliente(
        json.dumps(
            {
                "respuesta": "Aquí tienes",
                "derivar": False,
                "adjuntos": [{"tipo": "enlace", "clave": "clave_inventada"}],
            }
        ),
        ruta_recursos=ruta_recursos,
    )
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "¿tienen catálogo?")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    # El texto normal se envía igual; ningún envío enriquecido ocurre para la clave inventada.
    assert envios.llamadas == [("573001112233", "Aquí tienes")]
    assert envios_ubicacion.llamadas == []
    assert envios_cta_url.llamadas == []


def _escribir_recursos_con_imagen_webhook(tmp_path):
    ruta_imagen = tmp_path / "pan.jpg"
    ruta_imagen.write_bytes(b"\xff\xd8\xff\xe0JFIF")
    datos = {"imagenes": {"pan_del_dia": {"descripcion": "Foto del pan del día.", "archivo": "pan.jpg"}}}
    ruta = tmp_path / "recursos_imagen.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def test_adjunto_de_imagen_valido_se_envia_con_el_media_id_obtenido(
    fabrica_cliente, envios, envios_imagen, obtencion_media_id, tmp_path
):
    ruta_recursos = _escribir_recursos_con_imagen_webhook(tmp_path)
    cliente = fabrica_cliente(
        json.dumps(
            {
                "respuesta": "Aquí tienes la foto",
                "derivar": False,
                "adjuntos": [{"tipo": "imagen", "clave": "pan_del_dia"}],
            }
        ),
        ruta_recursos=ruta_recursos,
    )
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "¿tienen fotos del pan?")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", "Aquí tienes la foto")]
    assert obtencion_media_id.llamadas[0][0] == "pan_del_dia"
    assert envios_imagen.llamadas == [("573001112233", "media_de_prueba_123", "Foto del pan del día.")]


def test_si_falla_la_subida_de_la_imagen_el_texto_se_envia_igual(
    fabrica_cliente, envios, envios_imagen, tmp_path
):
    ruta_recursos = _escribir_recursos_con_imagen_webhook(tmp_path)
    media_id_fallido = ObtencionMediaIdFalsa(claves_que_fallan=("pan_del_dia",))
    cliente = fabrica_cliente(
        json.dumps(
            {
                "respuesta": "Aquí tienes la foto",
                "derivar": False,
                "adjuntos": [{"tipo": "imagen", "clave": "pan_del_dia"}],
            }
        ),
        ruta_recursos=ruta_recursos,
        obtener_media_id_fn=media_id_fallido,
    )
    payload = _payload_mensaje_texto("wamid.1", "573001112233", "¿tienen fotos del pan?")

    respuesta = _post_con_firma(cliente, payload)

    assert respuesta.status_code == 200
    assert envios.llamadas == [("573001112233", "Aquí tienes la foto")]
    assert envios_imagen.llamadas == []
