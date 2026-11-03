import logging

import requests

from env import obtener_env

logger = logging.getLogger(__name__)

TIEMPO_ESPERA_SEGUNDOS = 10


def _config_whatsapp():
    token = obtener_env("WHATSAPP_TOKEN")
    phone_number_id = obtener_env("WHATSAPP_PHONE_NUMBER_ID")
    version = obtener_env("GRAPH_API_VERSION")

    if not token or not phone_number_id or not version:
        raise ValueError(
            "Falta configuración de WhatsApp en el entorno "
            "(WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID o GRAPH_API_VERSION)."
        )
    return token, phone_number_id, version


def _enviar(cuerpo: dict) -> bool:
    token, phone_number_id, version = _config_whatsapp()
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    encabezados = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        respuesta = requests.post(
            url, json=cuerpo, headers=encabezados, timeout=TIEMPO_ESPERA_SEGUNDOS
        )
        respuesta.raise_for_status()
        return True
    except requests.exceptions.RequestException as error:
        codigo_estado = getattr(error.response, "status_code", None)
        error_meta = {}
        if error.response is not None:
            try:
                error_meta = error.response.json().get("error", {})
            except ValueError:
                error_meta = {}
        logger.error(
            "Fallo al enviar mensaje enriquecido de WhatsApp (tipo_mensaje=%s, tipo_error=%s, "
            "código=%s, error.code=%s, error.error_subcode=%s, error.message=%s)",
            cuerpo.get("type"),
            type(error).__name__,
            codigo_estado,
            error_meta.get("code"),
            error_meta.get("error_subcode"),
            error_meta.get("message"),
        )
        return False


def enviar_ubicacion(numero: str, latitud: float, longitud: float, nombre: str, direccion: str) -> bool:
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "location",
        "location": {
            "latitude": str(latitud),
            "longitude": str(longitud),
            "name": nombre,
            "address": direccion,
        },
    }
    return _enviar(cuerpo)


def enviar_imagen(numero: str, media_id: str, caption: str | None = None) -> bool:
    imagen: dict = {"id": media_id}
    if caption:
        imagen["caption"] = caption
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "image",
        "image": imagen,
    }
    return _enviar(cuerpo)


def enviar_cta_url(numero: str, texto_cuerpo: str, texto_boton: str, url: str) -> bool:
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": texto_cuerpo},
            "action": {
                "name": "cta_url",
                "parameters": {"display_text": texto_boton, "url": url},
            },
        },
    }
    return _enviar(cuerpo)
