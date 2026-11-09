"""Política de reintento compartida para las llamadas HTTP a la Graph API de
Meta (whatsapp.py, mensajes_enriquecidos.py, media_cache.py).

Solo reintenta en los dos casos donde el mensaje NO pudo haberse procesado del
lado de Meta, así que reintentar nunca lo duplica:
- requests.exceptions.ConnectionError: la petición nunca llegó a Meta.
- Un 429 explícito: Meta rechazó la petición por límite de tasa ANTES de
  procesarla (respeta la cabecera Retry-After si la envía).
Nunca reintenta ante un timeout (la respuesta pudo perderse después de que
Meta ya procesó el mensaje) ni ante ningún otro código de error."""
import logging
import time

import requests

logger = logging.getLogger(__name__)

INTENTOS_MAXIMOS = 3
ESPERA_INICIAL_SEGUNDOS = 1.0


def peticion_con_reintentos(hacer_peticion):
    """hacer_peticion() debe ejecutar la llamada de requests y su propio
    raise_for_status(), y devolver la respuesta. Reintenta unas pocas veces
    con espera corta y creciente ante ConnectionError o 429, registrando cada
    intento; en cualquier otro caso (u tras agotar los intentos) relanza la
    excepción tal cual, para que la llamen siga manejándola como hoy."""
    espera = ESPERA_INICIAL_SEGUNDOS
    for intento in range(1, INTENTOS_MAXIMOS + 1):
        try:
            return hacer_peticion()
        except requests.exceptions.ConnectionError:
            if intento == INTENTOS_MAXIMOS:
                raise
            logger.warning(
                "Fallo de conexión con Meta, reintento %d/%d en %.1fs.",
                intento, INTENTOS_MAXIMOS, espera,
            )
            time.sleep(espera)
            espera *= 2
        except requests.exceptions.HTTPError as error:
            codigo = getattr(error.response, "status_code", None)
            if codigo != 429 or intento == INTENTOS_MAXIMOS:
                raise
            espera_retry_after = None
            encabezado = error.response.headers.get("Retry-After") if error.response is not None else None
            if encabezado is not None:
                try:
                    espera_retry_after = float(encabezado)
                except ValueError:
                    espera_retry_after = None
            espera_real = max(espera, espera_retry_after or 0.0)
            logger.warning(
                "Límite de tasa (429) de Meta, reintento %d/%d en %.1fs.",
                intento, INTENTOS_MAXIMOS, espera_real,
            )
            time.sleep(espera_real)
            espera *= 2
