"""Servidor de prueba de carga para BotWhatsApp.

Construye la MISMA app Flask de producción (webhook.crear_app) pero con todo lo
externo sustituido por fakes con retraso configurable: nunca llama a Meta ni a
Anthropic de verdad, ni usa el secreto real ni la base de datos del volumen.

Se sirve con waitress, no gunicorn: gunicorn depende del módulo `fcntl` (solo
Unix) y no puede importarse en Windows. waitress es la alternativa más cercana
porque usa el mismo modelo de concurrencia que gunicorn --worker-class gthread
--workers 1 --threads N: un solo proceso con un pool de N hilos configurable
(aquí vía el parámetro `threads=`).

Este módulo queda fuera de la suite normal de pytest (vive en tests/carga/,
que no sigue el patrón test_*.py) y no se importa desde ningún test real.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from waitress.server import create_server

from almacenamiento import HistorialSQLite
from cerebro import Cerebro
from historial import HistorialMemoria
from llm.base import ProveedorIA
from pedidos import Pedidos
from recursos import cargar_recursos
from webhook import crear_app

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
RUTA_RECURSOS_TAMALES = RAIZ_PROYECTO / "recursos_tamales.json"
RUTA_PERFIL_TAMALES = RAIZ_PROYECTO / "perfil_tamales.md"

# Nunca el secreto real de Meta: este valor solo existe para que la prueba de
# carga pueda firmar sus propios payloads y que webhook._firma_valida los acepte.
SECRETO_PRUEBA = "secreto_de_prueba_no_real_para_carga"


class ProveedorIAFalso(ProveedorIA):
    """Nunca llama a Anthropic: duerme `retraso` segundos (imitando la latencia
    real de Claude) y devuelve siempre el mismo JSON válido fijo."""

    def __init__(self, retraso: float = 1.5) -> None:
        self._retraso = retraso

    def responder(self, sistema: str, mensajes: list[dict]) -> str:
        time.sleep(self._retraso)
        return '{"respuesta": "Mensaje de prueba de carga.", "derivar": false}'


class Registrador:
    """Guarda cada envío simulado (número destino, tipo, resumen, instante) de
    forma segura entre hilos, para poder verificar después que cada cliente
    recibió solo sus propios mensajes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._envios: list[tuple[str, str, str, float]] = []

    def registrar(self, numero: str, tipo: str, resumen: str) -> None:
        with self._lock:
            self._envios.append((numero, tipo, resumen, time.time()))

    def envios_de(self, numero: str) -> list[tuple[str, str, str, float]]:
        with self._lock:
            return [envio for envio in self._envios if envio[0] == numero]

    def todos(self) -> list[tuple[str, str, str, float]]:
        with self._lock:
            return list(self._envios)

    def numeros_distintos(self) -> set[str]:
        with self._lock:
            return {envio[0] for envio in self._envios}


def _fakes_meta(registrador: Registrador, retraso: float) -> dict:
    """Construye los puntos de inyección que webhook.crear_app/FlujoPedido usan
    para hablar con Meta, todos con el mismo retraso configurable (imitando la
    latencia real de la Graph API) y sin ninguna llamada de red real."""

    def enviar_texto_fn(numero, texto):
        time.sleep(retraso)
        registrador.registrar(numero, "texto", texto[:60])
        return True

    def enviar_botones_fn(numero, texto_cuerpo, botones):
        time.sleep(retraso)
        ids = ",".join(boton["id"] for boton in botones)
        registrador.registrar(numero, "botones", f"{texto_cuerpo[:40]} [{ids}]")
        return True

    def enviar_lista_fn(numero, texto_cuerpo, texto_boton, secciones):
        time.sleep(retraso)
        registrador.registrar(numero, "lista", texto_cuerpo[:40])
        return True

    def enviar_imagen_fn(numero, media_id, caption=None):
        time.sleep(retraso)
        registrador.registrar(numero, "imagen", (caption or "")[:60])
        return True

    def enviar_ubicacion_fn(numero, latitud, longitud, nombre, direccion):
        time.sleep(retraso)
        registrador.registrar(numero, "ubicacion", nombre)
        return True

    def enviar_cta_url_fn(numero, texto_cuerpo, texto_boton, url):
        time.sleep(retraso)
        registrador.registrar(numero, "cta_url", texto_cuerpo[:40])
        return True

    def obtener_media_id_fn(clave, ruta_archivo):
        time.sleep(retraso)
        return "media_id_de_prueba"

    def reenviar_media_fn(media_id_entrante):
        time.sleep(retraso)
        return "media_id_reenviado_de_prueba"

    return {
        "enviar_texto_fn": enviar_texto_fn,
        "enviar_botones_fn": enviar_botones_fn,
        "enviar_lista_fn": enviar_lista_fn,
        "enviar_imagen_fn": enviar_imagen_fn,
        "enviar_ubicacion_fn": enviar_ubicacion_fn,
        "enviar_cta_url_fn": enviar_cta_url_fn,
        "obtener_media_id_fn": obtener_media_id_fn,
        "reenviar_media_fn": reenviar_media_fn,
    }


def construir_app(
    ruta_bd_pedidos: Path,
    ruta_bd_historial: Path,
    registrador: Registrador,
    retraso_meta: float = 0.2,
    retraso_ia: float = 1.5,
    numero_dueno: str | None = None,
):
    """Arma la app de producción (webhook.crear_app) con fakes inyectados en
    TODOS los puntos que hoy hablan con Meta o con Anthropic. Nunca lee .env:
    solo fija META_APP_SECRET a un secreto de prueba, necesario para que
    webhook._firma_valida acepte los payloads que firma esta misma prueba."""
    os.environ["META_APP_SECRET"] = SECRETO_PRUEBA

    recursos = cargar_recursos(RUTA_RECURSOS_TAMALES)
    cerebro = Cerebro(
        ProveedorIAFalso(retraso_ia),
        HistorialMemoria(),
        ruta_negocio=RUTA_PERFIL_TAMALES,
        ruta_recursos=RUTA_RECURSOS_TAMALES,
    )
    fakes = _fakes_meta(registrador, retraso_meta)

    return crear_app(
        cerebro=cerebro,
        historial_dedup=HistorialSQLite(ruta_bd_historial),
        recursos=recursos,
        pedidos=Pedidos(ruta_bd_pedidos),
        perfil="tamales",
        mensaje_derivacion="Le comunico con una persona de nuestro equipo.",
        numero_dueno=numero_dueno,
        **fakes,
    )


class ServidorDePrueba:
    """Sirve una app Flask con waitress en un hilo en segundo plano, con un
    pool de hilos de tamaño configurable (equivalente a --threads de gunicorn)."""

    def __init__(self, app, host: str = "127.0.0.1", puerto: int = 8899, hilos: int = 4) -> None:
        self.puerto = puerto
        self._server = create_server(app, host=host, port=puerto, threads=hilos)
        self._hilo = threading.Thread(target=self._server.run, daemon=True)

    def iniciar(self) -> None:
        self._hilo.start()
        time.sleep(0.3)  # margen para que el socket quede escuchando

    def detener(self) -> None:
        self._server.close()
        time.sleep(0.2)
