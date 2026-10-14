import logging

import requests

from env import obtener_env

logger = logging.getLogger(__name__)

TIEMPO_ESPERA_SEGUNDOS = 10


def enviar_texto(numero: str, texto: str) -> bool:
    token = obtener_env("WHATSAPP_TOKEN")
    phone_number_id = obtener_env("WHATSAPP_PHONE_NUMBER_ID")
    version = obtener_env("GRAPH_API_VERSION")

    if not token or not phone_number_id or not version:
        raise ValueError(
            "Falta configuración de WhatsApp en el entorno "
            "(WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID o GRAPH_API_VERSION)."
        )

    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "text",
        "text": {"preview_url": False, "body": texto},
    }
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
            "Fallo al enviar mensaje de WhatsApp (tipo=%s, código=%s, "
            "error.code=%s, error.error_subcode=%s, error.message=%s)",
            type(error).__name__,
            codigo_estado,
            error_meta.get("code"),
            error_meta.get("error_subcode"),
            error_meta.get("message"),
        )
        return False
