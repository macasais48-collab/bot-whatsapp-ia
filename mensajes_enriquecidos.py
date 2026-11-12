import logging

import requests

from env import obtener_env
from red_meta import peticion_con_reintentos

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


def _enviar_con_wamid(cuerpo: dict) -> tuple[bool, str | None]:
    token, phone_number_id, version = _config_whatsapp()
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    encabezados = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    def _peticion():
        respuesta = requests.post(
            url, json=cuerpo, headers=encabezados, timeout=TIEMPO_ESPERA_SEGUNDOS
        )
        respuesta.raise_for_status()
        return respuesta

    try:
        respuesta = peticion_con_reintentos(_peticion)
        wamid = None
        try:
            wamid = respuesta.json()["messages"][0]["id"]
        except (ValueError, KeyError, IndexError, TypeError):
            wamid = None
        return True, wamid
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
        return False, None


def _enviar(cuerpo: dict) -> bool:
    return _enviar_con_wamid(cuerpo)[0]


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


def _cuerpo_imagen(numero: str, media_id: str, caption: str | None) -> dict:
    imagen: dict = {"id": media_id}
    if caption:
        imagen["caption"] = caption
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "image",
        "image": imagen,
    }


def enviar_imagen(numero: str, media_id: str, caption: str | None = None) -> bool:
    return _enviar(_cuerpo_imagen(numero, media_id, caption))


def enviar_imagen_con_wamid(numero: str, media_id: str, caption: str | None = None) -> tuple[bool, str | None]:
    # Mismo envío que enviar_imagen, pero devuelve también el wamid — solo para
    # el envío aparte de mejor esfuerzo del comprobante al dueño (ver
    # flujo_pedido._avisar_dueno), que necesita asociarlo al pedido para que un
    # "failed" posterior se loguee de forma informativa, no como "desconocido".
    return _enviar_con_wamid(_cuerpo_imagen(numero, media_id, caption))


def enviar_texto_con_wamid(numero: str, texto: str) -> tuple[bool, str | None]:
    # Mismo cuerpo que whatsapp.enviar_texto (que no cambia), pero devuelve
    # también el wamid — solo para los avisos de estado del pedido al cliente
    # (estado_pedido.avanzar_estado): un fallo por ventana de 24 horas (131047)
    # llega después, en un status "failed", y el wamid permite asociarlo al
    # pedido y registrarlo como informativo, no como "desconocido".
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "text",
        "text": {"preview_url": False, "body": texto},
    }
    return _enviar_con_wamid(cuerpo)


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


def enviar_botones(numero: str, texto_cuerpo: str, botones: list[dict]) -> bool:
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": texto_cuerpo},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": boton["id"], "title": boton["titulo"]}}
                    for boton in botones
                ]
            },
        },
    }
    return _enviar(cuerpo)


def enviar_lista(numero: str, texto_cuerpo: str, texto_boton: str, secciones: list[dict]) -> bool:
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": texto_cuerpo},
            "action": {
                "button": texto_boton,
                "sections": [
                    {
                        "title": seccion["titulo"],
                        "rows": [
                            {
                                "id": fila["id"],
                                "title": fila["titulo"],
                                "description": fila.get("descripcion", ""),
                            }
                            for fila in seccion["filas"]
                        ],
                    }
                    for seccion in secciones
                ],
            },
        },
    }
    return _enviar(cuerpo)


def enviar_plantilla(
    numero: str,
    nombre_plantilla: str,
    idioma: str,
    parametros_cuerpo: list[str],
    botones: list[str] | None = None,
) -> tuple[bool, str | None]:
    # Mensaje de plantilla (aprobado por Meta): la única forma de que un aviso
    # al dueño llegue siempre, incluso fuera de la ventana de 24 horas. `botones`
    # es la lista de payloads de los botones de respuesta rápida, en orden (el
    # índice de cada componente es su posición); None o [] = sin componentes de
    # botón (plantillas puramente informativas, como el aviso de pedido nuevo).
    # Ver docs/plantilla_aviso_dueno.md / docs/plantilla_aviso_pedido_nuevo.md
    # para las especificaciones exactas que Camilo crea en el WhatsApp Manager.
    componentes = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": texto} for texto in parametros_cuerpo],
        }
    ]
    for indice, payload in enumerate(botones or []):
        componentes.append(
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": str(indice),
                "parameters": [{"type": "payload", "payload": payload}],
            }
        )
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "template",
        "template": {
            "name": nombre_plantilla,
            "language": {"code": idioma},
            "components": componentes,
        },
    }
    return _enviar_con_wamid(cuerpo)
