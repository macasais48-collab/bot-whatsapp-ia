import sqlite3
from pathlib import Path

from basedatos import ejecutar
from env import obtener_env
from historial import Historial

RUTA_BD_POR_DEFECTO = Path(__file__).parent / "bot_whatsapp.db"


class HistorialSQLite(Historial):
    def __init__(self, ruta_bd: Path | str | None = None) -> None:
        if ruta_bd is None:
            ruta_bd = obtener_env("RUTA_BD") or RUTA_BD_POR_DEFECTO
        self._ruta_bd = str(ruta_bd)
        self._inicializar_tablas()

    def _inicializar_tablas(self) -> None:
        def _crear(conexion):
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_conversacion TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    texto TEXT NOT NULL,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS mensajes_procesados (
                    id_mensaje TEXT PRIMARY KEY,
                    procesado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        ejecutar(self._ruta_bd, _crear)

    def obtener(self, id_conversacion: str, limite: int) -> list[dict]:
        if limite <= 0:
            return []
        filas = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                """
                SELECT rol, texto FROM historial
                WHERE id_conversacion = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (id_conversacion, limite),
            ).fetchall(),
        )
        filas.reverse()
        return [{"role": rol, "content": texto} for rol, texto in filas]

    def agregar(self, id_conversacion: str, rol: str, texto: str) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "INSERT INTO historial (id_conversacion, rol, texto) VALUES (?, ?, ?)",
                (id_conversacion, rol, texto),
            ),
        )

    def marcar_si_nuevo(self, id_mensaje: str) -> bool:
        def _insertar(conexion):
            try:
                conexion.execute(
                    "INSERT INTO mensajes_procesados (id_mensaje) VALUES (?)",
                    (id_mensaje,),
                )
                return True
            except sqlite3.IntegrityError:
                return False

        return ejecutar(self._ruta_bd, _insertar)
