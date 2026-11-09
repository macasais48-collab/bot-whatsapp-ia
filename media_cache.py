import json
import logging
import time
from io import BytesIO
from pathlib import Path

import requests

from env import obtener_env
from red_meta import peticion_con_reintentos

logger = logging.getLogger(__name__)

TIEMPO_ESPERA_SEGUNDOS = 30
DIAS_VENCIMIENTO_MEDIA_ID = 25
SEGUNDOS_VENCIMIENTO_MEDIA_ID = DIAS_VENCIMIENTO_MEDIA_ID * 24 * 60 * 60

RUTA_CACHE_POR_DEFECTO = Path(__file__).parent / "media_id_cache.json"

TIPOS_MIME_POR_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _ruta_cache() -> Path:
    valor = obtener_env("RUTA_CACHE_MEDIA")
    return Path(valor) if valor else RUTA_CACHE_POR_DEFECTO


def _leer_cache(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("No se pudo leer el caché de media id (%s); se reconstruye.", ruta.name)
        return {}


def _escribir_cache(ruta: Path, cache: dict) -> None:
    ruta.write_text(json.dumps(cache), encoding="utf-8")


def _subir_bytes(contenido: bytes, nombre_archivo: str, tipo_mime: str) -> str | None:
    token = obtener_env("WHATSAPP_TOKEN")
    phone_number_id = obtener_env("WHATSAPP_PHONE_NUMBER_ID")
    version = obtener_env("GRAPH_API_VERSION")
    if not token or not phone_number_id or not version:
        raise ValueError(
            "Falta configuración de WhatsApp en el entorno "
            "(WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID o GRAPH_API_VERSION)."
        )

    url = f"https://graph.facebook.com/{version}/{phone_number_id}/media"
    encabezados = {"Authorization": f"Bearer {token}"}

    def _peticion():
        respuesta = requests.post(
            url,
            headers=encabezados,
            data={"messaging_product": "whatsapp"},
            files={"file": (nombre_archivo, BytesIO(contenido), tipo_mime)},
            timeout=TIEMPO_ESPERA_SEGUNDOS,
        )
        respuesta.raise_for_status()
        return respuesta

    try:
        respuesta = peticion_con_reintentos(_peticion)
        return respuesta.json()["id"]
    except requests.exceptions.RequestException as error:
        codigo_estado = getattr(error.response, "status_code", None)
        error_meta = {}
        if error.response is not None:
            try:
                error_meta = error.response.json().get("error", {})
            except ValueError:
                error_meta = {}
        logger.error(
            "Fallo al subir media a Meta (tipo_error=%s, código=%s, error.code=%s, "
            "error.error_subcode=%s, error.message=%s)",
            type(error).__name__,
            codigo_estado,
            error_meta.get("code"),
            error_meta.get("error_subcode"),
            error_meta.get("message"),
        )
        return None


def _subir_media(ruta_archivo: Path) -> str | None:
    tipo_mime = TIPOS_MIME_POR_EXTENSION.get(ruta_archivo.suffix.lower(), "application/octet-stream")
    with ruta_archivo.open("rb") as archivo:
        contenido = archivo.read()
    return _subir_bytes(contenido, ruta_archivo.name, tipo_mime)


def reenviar_media_entrante(media_id_entrante: str) -> str | None:
    """Descarga un media entrante de Meta (en memoria, nunca a disco) y lo vuelve a
    subir para obtener un media id que se pueda usar en un mensaje saliente a otro
    número — ver pago_pedido/flujo_pedido (aviso al dueño con el comprobante).
    Nunca escribe el contenido a disco ni a la base de datos (Ley 1581: el
    comprobante es un dato financiero del cliente). Nunca lanza por un fallo de
    red: si algo falla, se registra sin datos del remitente ni el contenido, y se
    devuelve None."""
    token = obtener_env("WHATSAPP_TOKEN")
    version = obtener_env("GRAPH_API_VERSION")
    if not token or not version:
        raise ValueError(
            "Falta configuración de WhatsApp en el entorno (WHATSAPP_TOKEN o GRAPH_API_VERSION)."
        )

    encabezados = {"Authorization": f"Bearer {token}"}

    def _pedir_metadata():
        respuesta = requests.get(
            f"https://graph.facebook.com/{version}/{media_id_entrante}",
            headers=encabezados,
            timeout=TIEMPO_ESPERA_SEGUNDOS,
        )
        respuesta.raise_for_status()
        return respuesta

    def _descargar(url_descarga):
        def _peticion():
            respuesta = requests.get(url_descarga, headers=encabezados, timeout=TIEMPO_ESPERA_SEGUNDOS)
            respuesta.raise_for_status()
            return respuesta

        return peticion_con_reintentos(_peticion)

    try:
        respuesta_media = peticion_con_reintentos(_pedir_metadata)
        datos_media = respuesta_media.json()
        url_descarga = datos_media["url"]
        tipo_mime = datos_media.get("mime_type", "application/octet-stream")

        respuesta_descarga = _descargar(url_descarga)
        contenido = respuesta_descarga.content
    except (requests.exceptions.RequestException, KeyError, ValueError) as error:
        logger.error(
            "Fallo al descargar un media entrante para reenviarlo (tipo_error=%s).",
            type(error).__name__,
        )
        return None

    return _subir_bytes(contenido, "comprobante", tipo_mime)


def obtener_media_id(clave: str, ruta_archivo: Path, reloj=time.time) -> str | None:
    """Devuelve un media id vigente para 'clave', resubiendo a Meta si falta o
    si el que hay en caché tiene más de DIAS_VENCIMIENTO_MEDIA_ID días. Nunca lanza
    por un fallo de red: si la subida falla, se registra y se devuelve None."""
    ruta_cache = _ruta_cache()
    cache = _leer_cache(ruta_cache)
    entrada = cache.get(clave)

    if entrada is not None:
        antiguedad_segundos = reloj() - entrada.get("subido_en", 0)
        if antiguedad_segundos < SEGUNDOS_VENCIMIENTO_MEDIA_ID:
            return entrada["media_id"]

    media_id = _subir_media(ruta_archivo)
    if media_id is None:
        return None

    cache[clave] = {"media_id": media_id, "subido_en": reloj()}
    _escribir_cache(ruta_cache, cache)
    return media_id
