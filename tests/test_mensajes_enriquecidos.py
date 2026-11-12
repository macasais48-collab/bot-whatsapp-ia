import requests

from mensajes_enriquecidos import enviar_imagen_con_wamid, enviar_plantilla


class _RespuestaFalsa:
    def __init__(self, cuerpo_json):
        self._cuerpo_json = cuerpo_json

    def raise_for_status(self):
        pass

    def json(self):
        return self._cuerpo_json


def _configurar_env(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "token_secreto_de_prueba_no_debe_aparecer")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("GRAPH_API_VERSION", "v26.0")


def test_enviar_plantilla_construye_el_cuerpo_correcto_y_devuelve_el_wamid(monkeypatch):
    _configurar_env(monkeypatch)
    cuerpos_enviados = []

    def post_falso(url, json, headers, timeout):
        cuerpos_enviados.append(json)
        return _RespuestaFalsa({"messages": [{"id": "wamid.ABC123"}]})

    monkeypatch.setattr("mensajes_enriquecidos.requests.post", post_falso)

    ok, wamid = enviar_plantilla(
        "573001112233",
        "aviso_pago_pendiente_verificacion",
        "es",
        ["42", "$45.000"],
        botones=["pago_recibido_42", "pago_no_llego_42"],
    )

    assert ok is True
    assert wamid == "wamid.ABC123"
    cuerpo = cuerpos_enviados[0]
    assert cuerpo["type"] == "template"
    assert cuerpo["template"]["name"] == "aviso_pago_pendiente_verificacion"
    assert cuerpo["template"]["language"] == {"code": "es"}
    componentes = cuerpo["template"]["components"]
    assert componentes[0] == {
        "type": "body",
        "parameters": [{"type": "text", "text": "42"}, {"type": "text", "text": "$45.000"}],
    }
    assert componentes[1] == {
        "type": "button", "sub_type": "quick_reply", "index": "0",
        "parameters": [{"type": "payload", "payload": "pago_recibido_42"}],
    }
    assert componentes[2] == {
        "type": "button", "sub_type": "quick_reply", "index": "1",
        "parameters": [{"type": "payload", "payload": "pago_no_llego_42"}],
    }


def test_enviar_plantilla_sin_botones_no_agrega_componentes_de_boton(monkeypatch):
    _configurar_env(monkeypatch)
    cuerpos_enviados = []

    def post_falso(url, json, headers, timeout):
        cuerpos_enviados.append(json)
        return _RespuestaFalsa({"messages": [{"id": "wamid.DEF456"}]})

    monkeypatch.setattr("mensajes_enriquecidos.requests.post", post_falso)

    ok, wamid = enviar_plantilla("573001112233", "aviso_pedido_nuevo", "es", ["1", "2", "3", "4", "5", "6"])

    assert ok is True
    assert wamid == "wamid.DEF456"
    componentes = cuerpos_enviados[0]["template"]["components"]
    assert len(componentes) == 1
    assert componentes[0]["type"] == "body"


def test_enviar_plantilla_devuelve_false_y_ningun_wamid_ante_un_error(monkeypatch):
    _configurar_env(monkeypatch)

    def post_falso(*args, **kwargs):
        raise requests.exceptions.HTTPError(response=None)

    monkeypatch.setattr("mensajes_enriquecidos.requests.post", post_falso)

    ok, wamid = enviar_plantilla("573001112233", "x", "es", ["1", "2"], botones=["pago_recibido_1", "pago_no_llego_1"])

    assert ok is False
    assert wamid is None


def test_enviar_imagen_con_wamid_devuelve_exito_y_wamid(monkeypatch):
    _configurar_env(monkeypatch)

    def post_falso(url, json, headers, timeout):
        assert json["type"] == "image"
        assert json["image"]["id"] == "media-123"
        return _RespuestaFalsa({"messages": [{"id": "wamid.XYZ"}]})

    monkeypatch.setattr("mensajes_enriquecidos.requests.post", post_falso)

    ok, wamid = enviar_imagen_con_wamid("573001112233", "media-123", caption="Comprobante del pedido #7")

    assert ok is True
    assert wamid == "wamid.XYZ"


def test_enviar_imagen_con_wamid_devuelve_false_y_ningun_wamid_ante_un_error(monkeypatch):
    _configurar_env(monkeypatch)
    monkeypatch.setattr("red_meta.time.sleep", lambda segundos: None)

    def post_falso(*args, **kwargs):
        raise requests.exceptions.ConnectionError("sin red")

    monkeypatch.setattr("mensajes_enriquecidos.requests.post", post_falso)

    ok, wamid = enviar_imagen_con_wamid("573001112233", "media-123")

    assert ok is False
    assert wamid is None
