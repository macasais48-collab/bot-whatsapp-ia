"""Conexión SQLite compartida entre almacenamiento.py y pedidos.py: modo WAL
(permite lectores concurrentes mientras hay un escritor, a diferencia del modo
por defecto, que bloquea todo el archivo para cualquiera) + busy_timeout
explícito, con un reintento corto y creciente si de todas formas aparece
"database is locked" (dos escrituras realmente simultáneas, p. ej. un cliente
confirmando un pedido mientras otro conversa con la IA) -- para que un mensaje
nunca se pierda en silencio por esta causa. Ver análisis de rendimiento del
8/11/2026: historial y pedidos comparten un solo archivo (RUTA_BD) en
producción, así que ambos módulos pasan por aquí."""
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_MS = 5000
INTENTOS_ANTE_BLOQUEO = 3
ESPERA_INICIAL_SEGUNDOS = 0.1


@contextmanager
def _conectar(ruta_bd: Path | str):
    conexion = sqlite3.connect(ruta_bd, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        conexion.execute("PRAGMA journal_mode=WAL")
        conexion.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        yield conexion
    finally:
        conexion.close()


def ejecutar(ruta_bd: Path | str, operacion):
    """Abre una conexión con WAL + busy_timeout, ejecuta operacion(conexion)
    dentro de una transacción (commit si termina bien, rollback si lanza) y
    devuelve su resultado. Si SQLite devuelve "database is locked", reintenta
    unas pocas veces con espera corta y creciente, registrando cada intento;
    si se agotan los reintentos, relanza la excepción -- nunca se traga el
    error en silencio."""
    espera = ESPERA_INICIAL_SEGUNDOS
    for intento in range(1, INTENTOS_ANTE_BLOQUEO + 1):
        try:
            with _conectar(ruta_bd) as conexion:
                with conexion:
                    return operacion(conexion)
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or intento == INTENTOS_ANTE_BLOQUEO:
                raise
            logger.warning(
                "Base de datos bloqueada, reintento %d/%d en %.1fs.",
                intento, INTENTOS_ANTE_BLOQUEO, espera,
            )
            time.sleep(espera)
            espera *= 2
