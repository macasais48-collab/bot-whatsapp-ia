"""Tabla de citas (sub-fase 7a) en el mismo archivo SQLite que pedidos.

- Una sola cita en construcción por número (crear una nueva cancela la anterior).
- La reserva del cupo es atómica, en una sola sentencia (mismo patrón que
  `Pedidos.reservar_reporte`): confirma solo si el horario todavía tiene cupo y
  el cliente no llegó a su tope de citas futuras. SQLite serializa los
  escritores, así que dos clientes nunca toman de más el mismo cupo.
- La aceptación del tratamiento de datos (Ley 1581) queda con fecha y hora en
  `consentimiento_en`.
- Retención: `borrar_datos_vencidos` quita los datos personales (datos de la
  cita y teléfono) y conserva fecha, hora y estado para estadísticas.
- Recordatorio al cliente (sub-fase 7b.1): `recordatorio_enviado_en` se marca
  en una sola sentencia (`reservar_recordatorio`) antes de enviar, así el mismo
  recordatorio nunca sale dos veces aunque dos revisiones coincidan.

Nunca registra en el log teléfonos completos ni datos de la cita.
"""
import json
from pathlib import Path

from basedatos import ejecutar
from env import obtener_env
from pedidos import RUTA_BD_POR_DEFECTO

ESTADO_EN_CONSTRUCCION = "en_construccion"
ESTADO_CONFIRMADA = "confirmada"
ESTADO_CANCELADA = "cancelada"

PASO_INICIAL = "dia"

# Resultados de `confirmar`.
RESULTADO_CONFIRMADA = "confirmada"
RESULTADO_CUPO_LLENO = "cupo_lleno"
RESULTADO_TOPE_CLIENTE = "tope_cliente"
RESULTADO_NO_EN_CONSTRUCCION = "no_en_construccion"
RESULTADO_SIN_HORARIO = "sin_horario"

_COLUMNAS = (
    "id, numero_cliente, perfil, estado, paso, fecha, inicio, datos_json, "
    "consentimiento_en, wamid_aviso_dueno, creado_en, actualizado_en, "
    "recordatorio_enviado_en, wamid_recordatorio"
)

# Columnas agregadas después de crear la tabla (sub-fase 7b.1): se suman con
# ALTER TABLE a una base existente, sin tocar sus datos.
_COLUMNAS_AGREGADAS = (
    ("recordatorio_enviado_en", "REAL"),
    ("wamid_recordatorio", "TEXT"),
)


class Citas:
    def __init__(self, ruta_bd: Path | str | None = None) -> None:
        if ruta_bd is None:
            ruta_bd = obtener_env("RUTA_BD") or RUTA_BD_POR_DEFECTO
        self._ruta_bd = str(ruta_bd)
        self._inicializar_tablas()

    def _inicializar_tablas(self) -> None:
        def _crear(conexion):
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS citas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_cliente TEXT NOT NULL,
                    perfil TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    paso TEXT NOT NULL,
                    fecha TEXT,
                    inicio TEXT,
                    datos_json TEXT,
                    consentimiento_en REAL,
                    wamid_aviso_dueno TEXT,
                    creado_en REAL NOT NULL,
                    actualizado_en REAL NOT NULL
                )
                """
            )
            conexion.execute("CREATE INDEX IF NOT EXISTS idx_citas_cupo ON citas (perfil, inicio, estado)")
            conexion.execute("CREATE INDEX IF NOT EXISTS idx_citas_numero ON citas (numero_cliente, estado)")
            existentes = {fila[1] for fila in conexion.execute("PRAGMA table_info(citas)")}
            for columna, tipo in _COLUMNAS_AGREGADAS:
                if columna not in existentes:
                    conexion.execute(f"ALTER TABLE citas ADD COLUMN {columna} {tipo}")

        ejecutar(self._ruta_bd, _crear)

    # -- Lectura --

    @staticmethod
    def _fila_a_dict(fila) -> dict:
        (
            id_cita, numero_cliente, perfil, estado, paso, fecha, inicio, datos_json,
            consentimiento_en, wamid_aviso_dueno, creado_en, actualizado_en,
            recordatorio_enviado_en, wamid_recordatorio,
        ) = fila
        return {
            "id": id_cita,
            "numero_cliente": numero_cliente,
            "perfil": perfil,
            "estado": estado,
            "paso": paso,
            "fecha": fecha,
            "inicio": inicio,
            "datos": json.loads(datos_json) if datos_json else {},
            "consentimiento_en": consentimiento_en,
            "wamid_aviso_dueno": wamid_aviso_dueno,
            "creado_en": creado_en,
            "actualizado_en": actualizado_en,
            "recordatorio_enviado_en": recordatorio_enviado_en,
            "wamid_recordatorio": wamid_recordatorio,
        }

    def obtener(self, cita_id: int) -> dict | None:
        fila = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(f"SELECT {_COLUMNAS} FROM citas WHERE id = ?", (cita_id,)).fetchone(),
        )
        return self._fila_a_dict(fila) if fila is not None else None

    def obtener_en_construccion(self, numero_cliente: str) -> dict | None:
        fila = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                f"SELECT {_COLUMNAS} FROM citas WHERE numero_cliente = ? AND estado = ? ORDER BY id DESC LIMIT 1",
                (numero_cliente, ESTADO_EN_CONSTRUCCION),
            ).fetchone(),
        )
        return self._fila_a_dict(fila) if fila is not None else None

    def ocupacion(self, perfil: str, desde: str, hasta: str) -> dict:
        """{inicio: citas confirmadas} entre `desde` y `hasta` (inclusivos,
        'YYYY-MM-DD HH:MM'), en una sola consulta."""
        filas = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                """
                SELECT inicio, COUNT(*) FROM citas
                WHERE perfil = ? AND estado = ? AND inicio >= ? AND inicio <= ?
                GROUP BY inicio
                """,
                (perfil, ESTADO_CONFIRMADA, desde, hasta),
            ).fetchall(),
        )
        return {inicio: cantidad for inicio, cantidad in filas}

    def listar_proximas(
        self, perfil: str, desde_inicio: str, desplazamiento: int = 0, limite: int | None = None
    ) -> list[dict]:
        """Citas confirmadas desde `desde_inicio`, de la más próxima a la más lejana."""
        consulta = (
            f"SELECT {_COLUMNAS} FROM citas WHERE perfil = ? AND estado = ? AND inicio >= ? "
            "ORDER BY inicio ASC, id ASC LIMIT ? OFFSET ?"
        )
        filas = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                consulta,
                (perfil, ESTADO_CONFIRMADA, desde_inicio, -1 if limite is None else limite, desplazamiento),
            ).fetchall(),
        )
        return [self._fila_a_dict(fila) for fila in filas]

    def contar_futuras_del_cliente(self, numero_cliente: str, perfil: str, desde_inicio: str) -> int:
        return ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "SELECT COUNT(*) FROM citas WHERE numero_cliente = ? AND perfil = ? AND estado = ? AND inicio >= ?",
                (numero_cliente, perfil, ESTADO_CONFIRMADA, desde_inicio),
            ).fetchone()[0],
        )

    def cita_por_wamid_aviso(self, wamid: str) -> int | None:
        fila = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "SELECT id FROM citas WHERE wamid_aviso_dueno = ?", (wamid,)
            ).fetchone(),
        )
        return fila[0] if fila is not None else None

    def pendientes_de_recordatorio(self, perfil: str, desde_inicio: str, hasta_inicio: str) -> list[dict]:
        """Citas confirmadas, con teléfono, sin recordatorio enviado y con
        horario entre `desde_inicio` y `hasta_inicio` (inclusivos)."""
        filas = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                f"""
                SELECT {_COLUMNAS} FROM citas
                WHERE perfil = ? AND estado = ? AND recordatorio_enviado_en IS NULL
                  AND numero_cliente != '' AND inicio >= ? AND inicio <= ?
                ORDER BY inicio ASC, id ASC
                """,
                (perfil, ESTADO_CONFIRMADA, desde_inicio, hasta_inicio),
            ).fetchall(),
        )
        return [self._fila_a_dict(fila) for fila in filas]

    def cita_por_wamid_recordatorio(self, wamid: str) -> int | None:
        fila = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "SELECT id FROM citas WHERE wamid_recordatorio = ?", (wamid,)
            ).fetchone(),
        )
        return fila[0] if fila is not None else None

    # -- Escritura de la cita en construcción --

    def crear_en_construccion(self, numero_cliente: str, perfil: str, ahora: float) -> int:
        """Crea la cita en construcción del número, cancelando antes cualquier
        otra en construcción (nunca hay dos)."""
        def _crear(conexion):
            conexion.execute(
                "UPDATE citas SET estado = ?, actualizado_en = ? WHERE numero_cliente = ? AND estado = ?",
                (ESTADO_CANCELADA, ahora, numero_cliente, ESTADO_EN_CONSTRUCCION),
            )
            return conexion.execute(
                """
                INSERT INTO citas (numero_cliente, perfil, estado, paso, creado_en, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (numero_cliente, perfil, ESTADO_EN_CONSTRUCCION, PASO_INICIAL, ahora, ahora),
            ).lastrowid

        return ejecutar(self._ruta_bd, _crear)

    def _actualizar_en_construccion(self, cita_id: int, campos: dict, ahora: float) -> bool:
        asignaciones = ", ".join(f"{columna} = ?" for columna in campos)
        valores = (*campos.values(), ahora, cita_id, ESTADO_EN_CONSTRUCCION)
        return ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                f"UPDATE citas SET {asignaciones}, actualizado_en = ? WHERE id = ? AND estado = ?",
                valores,
            ).rowcount,
        ) == 1

    def fijar_paso(self, cita_id: int, paso: str, ahora: float) -> bool:
        return self._actualizar_en_construccion(cita_id, {"paso": paso}, ahora)

    def fijar_fecha(self, cita_id: int, fecha: str, paso: str, ahora: float) -> bool:
        # Cambiar de día borra la hora elegida antes.
        return self._actualizar_en_construccion(cita_id, {"fecha": fecha, "inicio": None, "paso": paso}, ahora)

    def fijar_inicio(self, cita_id: int, inicio: str, paso: str, ahora: float) -> bool:
        return self._actualizar_en_construccion(cita_id, {"inicio": inicio, "paso": paso}, ahora)

    def registrar_consentimiento(self, cita_id: int, paso: str, ahora: float) -> bool:
        return self._actualizar_en_construccion(cita_id, {"consentimiento_en": ahora, "paso": paso}, ahora)

    def guardar_dato(self, cita_id: int, clave: str, valor: str, paso: str, ahora: float) -> bool:
        def _guardar(conexion):
            fila = conexion.execute(
                "SELECT datos_json FROM citas WHERE id = ? AND estado = ?", (cita_id, ESTADO_EN_CONSTRUCCION)
            ).fetchone()
            if fila is None:
                return 0
            datos = json.loads(fila[0]) if fila[0] else {}
            datos[clave] = valor
            return conexion.execute(
                "UPDATE citas SET datos_json = ?, paso = ?, actualizado_en = ? WHERE id = ? AND estado = ?",
                (json.dumps(datos, ensure_ascii=False), paso, ahora, cita_id, ESTADO_EN_CONSTRUCCION),
            ).rowcount

        return ejecutar(self._ruta_bd, _guardar) == 1

    # -- Reserva atómica --

    def confirmar(
        self, cita_id: int, cupos_por_horario: int, max_citas_por_cliente: int, desde_inicio: str, ahora: float
    ) -> str:
        """Confirma la cita en UNA sola sentencia, solo si: sigue en
        construcción, tiene horario, el horario no está lleno y el cliente
        tiene menos de `max_citas_por_cliente` citas futuras (desde
        `desde_inicio`). Devuelve uno de los RESULTADO_*; si no confirma, el
        motivo se diagnostica después solo para elegir el mensaje."""
        def _confirmar(conexion):
            cambios = conexion.execute(
                """
                UPDATE citas SET estado = ?, actualizado_en = ?
                WHERE id = ? AND estado = ? AND inicio IS NOT NULL
                  AND (SELECT COUNT(*) FROM citas AS otra
                        WHERE otra.perfil = citas.perfil AND otra.inicio = citas.inicio
                          AND otra.estado = ?) < ?
                  AND (SELECT COUNT(*) FROM citas AS otra
                        WHERE otra.numero_cliente = citas.numero_cliente AND otra.perfil = citas.perfil
                          AND otra.estado = ? AND otra.inicio >= ?) < ?
                """,
                (
                    ESTADO_CONFIRMADA, ahora,
                    cita_id, ESTADO_EN_CONSTRUCCION,
                    ESTADO_CONFIRMADA, cupos_por_horario,
                    ESTADO_CONFIRMADA, desde_inicio, max_citas_por_cliente,
                ),
            ).rowcount
            if cambios == 1:
                return RESULTADO_CONFIRMADA

            fila = conexion.execute(
                "SELECT numero_cliente, perfil, estado, inicio FROM citas WHERE id = ?", (cita_id,)
            ).fetchone()
            if fila is None or fila[2] != ESTADO_EN_CONSTRUCCION:
                return RESULTADO_NO_EN_CONSTRUCCION
            numero_cliente, perfil, _, inicio = fila
            if inicio is None:
                return RESULTADO_SIN_HORARIO
            futuras = conexion.execute(
                "SELECT COUNT(*) FROM citas WHERE numero_cliente = ? AND perfil = ? AND estado = ? AND inicio >= ?",
                (numero_cliente, perfil, ESTADO_CONFIRMADA, desde_inicio),
            ).fetchone()[0]
            if futuras >= max_citas_por_cliente:
                return RESULTADO_TOPE_CLIENTE
            return RESULTADO_CUPO_LLENO

        return ejecutar(self._ruta_bd, _confirmar)

    def cancelar(self, cita_id: int, ahora: float) -> bool:
        """Cancela una cita en construcción o confirmada (la salida de
        emergencia del dueño usa esto). Devuelve False si no existía o ya
        estaba cancelada."""
        return ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE citas SET estado = ?, actualizado_en = ? WHERE id = ? AND estado IN (?, ?)",
                (ESTADO_CANCELADA, ahora, cita_id, ESTADO_EN_CONSTRUCCION, ESTADO_CONFIRMADA),
            ).rowcount,
        ) == 1

    def fijar_wamid_aviso(self, cita_id: int, wamid: str) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE citas SET wamid_aviso_dueno = ? WHERE id = ?", (wamid, cita_id)
            ),
        )

    # -- Recordatorio al cliente (sub-fase 7b.1) --

    def reservar_recordatorio(self, cita_id: int, ahora: float) -> bool:
        """Marca el recordatorio como enviado solo si la cita sigue confirmada
        y no lo tenía: True = esta llamada lo reservó y debe enviarlo."""
        return ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE citas SET recordatorio_enviado_en = ? "
                "WHERE id = ? AND estado = ? AND recordatorio_enviado_en IS NULL",
                (ahora, cita_id, ESTADO_CONFIRMADA),
            ).rowcount,
        ) == 1

    def liberar_recordatorio(self, cita_id: int) -> None:
        """Quita la marca si el envío falló (Meta no lo aceptó), para
        reintentarlo en la siguiente revisión."""
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE citas SET recordatorio_enviado_en = NULL, wamid_recordatorio = NULL WHERE id = ?",
                (cita_id,),
            ),
        )

    def fijar_wamid_recordatorio(self, cita_id: int, wamid: str) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE citas SET wamid_recordatorio = ? WHERE id = ?", (wamid, cita_id)
            ),
        )

    # -- Retención (Ley 1581) --

    def borrar_datos_vencidos(self, perfil: str, limite_inicio: str, limite_actualizado: float) -> int:
        """Borra los datos personales (datos de la cita y teléfono) de:
        - las citas confirmadas con horario anterior a `limite_inicio` (hoy
          menos `retencion_dias`), y
        - las que no se confirmaron (canceladas o abandonadas en construcción)
          y no se tocan desde antes de `limite_actualizado`.
        Conserva id, perfil, estado, fecha, hora y fechas de registro, para
        estadísticas. Devuelve cuántas citas se anonimizaron."""
        return ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                """
                UPDATE citas SET datos_json = NULL, numero_cliente = ''
                WHERE perfil = ? AND (datos_json IS NOT NULL OR numero_cliente != '')
                  AND ((estado = ? AND inicio < ?)
                       OR (estado != ? AND actualizado_en < ?))
                """,
                (perfil, ESTADO_CONFIRMADA, limite_inicio, ESTADO_CONFIRMADA, limite_actualizado),
            ).rowcount,
        )
