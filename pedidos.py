from pathlib import Path

from basedatos import ejecutar
from env import obtener_env

RUTA_BD_POR_DEFECTO = Path(__file__).parent / "bot_whatsapp.db"

ESTADO_EN_CONSTRUCCION = "en_construccion"
ESTADO_RECIBIDO = "recibido"
ESTADO_CANCELADO = "cancelado"
ESTADO_PAGO_PENDIENTE = "pago_pendiente"
ESTADO_PAGO_POR_VERIFICAR = "pago_por_verificar"
ESTADO_PAGADO = "pagado"

ESTADOS_ACTIVOS = (ESTADO_EN_CONSTRUCCION, ESTADO_PAGO_PENDIENTE, ESTADO_PAGO_POR_VERIFICAR)

PASO_INICIAL = "producto"


class Pedidos:
    def __init__(self, ruta_bd: Path | str | None = None) -> None:
        if ruta_bd is None:
            ruta_bd = obtener_env("RUTA_BD") or RUTA_BD_POR_DEFECTO
        self._ruta_bd = str(ruta_bd)
        self._inicializar_tablas()

    def _inicializar_tablas(self) -> None:
        def _crear(conexion):
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS pedidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_cliente TEXT NOT NULL,
                    perfil TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    paso TEXT NOT NULL,
                    producto_pendiente TEXT,
                    consentimiento_aceptado INTEGER,
                    tipo_entrega TEXT,
                    zona_domicilio TEXT,
                    direccion_texto TEXT,
                    latitud REAL,
                    longitud REAL,
                    total INTEGER,
                    metodo_pago TEXT,
                    creado_en REAL NOT NULL,
                    actualizado_en REAL NOT NULL
                )
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS pedido_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pedido_id INTEGER NOT NULL,
                    clave_producto TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    precio_unitario INTEGER NOT NULL,
                    cantidad INTEGER NOT NULL,
                    subtotal INTEGER NOT NULL
                )
                """
            )
            # Migración defensiva: una base ya creada antes de la sub-fase 4 (pago
            # asistido) tiene la tabla 'pedidos' sin 'metodo_pago' — CREATE TABLE IF
            # NOT EXISTS no la modifica, así que se agrega la columna si falta, sin
            # tocar los pedidos ya guardados.
            columnas_existentes = {
                fila[1] for fila in conexion.execute("PRAGMA table_info(pedidos)").fetchall()
            }
            if "metodo_pago" not in columnas_existentes:
                conexion.execute("ALTER TABLE pedidos ADD COLUMN metodo_pago TEXT")

        ejecutar(self._ruta_bd, _crear)

    def _fila_a_dict(self, fila) -> dict:
        (
            id_pedido,
            numero_cliente,
            perfil,
            estado,
            paso,
            producto_pendiente,
            consentimiento_aceptado,
            tipo_entrega,
            zona_domicilio,
            direccion_texto,
            latitud,
            longitud,
            total,
            metodo_pago,
            creado_en,
            actualizado_en,
        ) = fila
        items = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                """
                SELECT clave_producto, nombre, precio_unitario, cantidad, subtotal
                FROM pedido_items WHERE pedido_id = ? ORDER BY id ASC
                """,
                (id_pedido,),
            ).fetchall(),
        )
        return {
            "id": id_pedido,
            "numero_cliente": numero_cliente,
            "perfil": perfil,
            "estado": estado,
            "paso": paso,
            "producto_pendiente": producto_pendiente,
            "consentimiento_aceptado": bool(consentimiento_aceptado) if consentimiento_aceptado is not None else None,
            "tipo_entrega": tipo_entrega,
            "zona_domicilio": zona_domicilio,
            "direccion_texto": direccion_texto,
            "latitud": latitud,
            "longitud": longitud,
            "total": total,
            "metodo_pago": metodo_pago,
            "creado_en": creado_en,
            "actualizado_en": actualizado_en,
            "items": [
                {
                    "clave_producto": clave_producto,
                    "nombre": nombre,
                    "precio_unitario": precio_unitario,
                    "cantidad": cantidad,
                    "subtotal": subtotal,
                }
                for clave_producto, nombre, precio_unitario, cantidad, subtotal in items
            ],
        }

    _COLUMNAS_PEDIDO = (
        "id, numero_cliente, perfil, estado, paso, producto_pendiente, "
        "consentimiento_aceptado, tipo_entrega, zona_domicilio, direccion_texto, "
        "latitud, longitud, total, metodo_pago, creado_en, actualizado_en"
    )

    def obtener_en_construccion(self, numero_cliente: str) -> dict | None:
        fila = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                f"""
                SELECT {self._COLUMNAS_PEDIDO}
                FROM pedidos
                WHERE numero_cliente = ? AND estado = ?
                ORDER BY id DESC LIMIT 1
                """,
                (numero_cliente, ESTADO_EN_CONSTRUCCION),
            ).fetchone(),
        )
        if fila is None:
            return None
        return self._fila_a_dict(fila)

    def obtener_activo(self, numero_cliente: str) -> dict | None:
        marcadores = ", ".join("?" for _ in ESTADOS_ACTIVOS)
        fila = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                f"""
                SELECT {self._COLUMNAS_PEDIDO}
                FROM pedidos
                WHERE numero_cliente = ? AND estado IN ({marcadores})
                ORDER BY id DESC LIMIT 1
                """,
                (numero_cliente, *ESTADOS_ACTIVOS),
            ).fetchone(),
        )
        if fila is None:
            return None
        return self._fila_a_dict(fila)

    def obtener(self, pedido_id: int) -> dict | None:
        fila = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                f"SELECT {self._COLUMNAS_PEDIDO} FROM pedidos WHERE id = ?",
                (pedido_id,),
            ).fetchone(),
        )
        if fila is None:
            return None
        return self._fila_a_dict(fila)

    def listar_por_estados(self, estados: list[str]) -> list[dict]:
        marcadores = ", ".join("?" for _ in estados)
        filas = ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                f"""
                SELECT {self._COLUMNAS_PEDIDO}
                FROM pedidos
                WHERE estado IN ({marcadores})
                ORDER BY id ASC
                """,
                tuple(estados),
            ).fetchall(),
        )
        return [self._fila_a_dict(fila) for fila in filas]

    def crear_en_construccion(self, numero_cliente: str, perfil: str, ahora: float) -> int:
        return ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                """
                INSERT INTO pedidos (
                    numero_cliente, perfil, estado, paso, creado_en, actualizado_en
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (numero_cliente, perfil, ESTADO_EN_CONSTRUCCION, PASO_INICIAL, ahora, ahora),
            ).lastrowid,
        )

    def fijar_paso(self, pedido_id: int, paso: str, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET paso = ?, actualizado_en = ? WHERE id = ?",
                (paso, ahora, pedido_id),
            ),
        )

    def fijar_producto_pendiente(self, pedido_id: int, clave_producto: str, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET producto_pendiente = ?, paso = 'cantidad', actualizado_en = ? WHERE id = ?",
                (clave_producto, ahora, pedido_id),
            ),
        )

    def agregar_item(
        self,
        pedido_id: int,
        clave_producto: str,
        nombre: str,
        precio_unitario: int,
        cantidad: int,
        ahora: float,
    ) -> None:
        subtotal = precio_unitario * cantidad

        def _operacion(conexion):
            conexion.execute(
                """
                INSERT INTO pedido_items (pedido_id, clave_producto, nombre, precio_unitario, cantidad, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (pedido_id, clave_producto, nombre, precio_unitario, cantidad, subtotal),
            )
            conexion.execute(
                "UPDATE pedidos SET producto_pendiente = NULL, paso = 'agregar_otro_o_continuar', "
                "actualizado_en = ? WHERE id = ?",
                (ahora, pedido_id),
            )

        ejecutar(self._ruta_bd, _operacion)

    def vaciar_items(self, pedido_id: int, ahora: float) -> None:
        def _operacion(conexion):
            conexion.execute("DELETE FROM pedido_items WHERE pedido_id = ?", (pedido_id,))
            conexion.execute(
                """
                UPDATE pedidos SET
                    producto_pendiente = NULL,
                    tipo_entrega = NULL,
                    zona_domicilio = NULL,
                    direccion_texto = NULL,
                    latitud = NULL,
                    longitud = NULL,
                    paso = ?,
                    actualizado_en = ?
                WHERE id = ?
                """,
                (PASO_INICIAL, ahora, pedido_id),
            )

        ejecutar(self._ruta_bd, _operacion)

    def fijar_consentimiento(self, pedido_id: int, aceptado: bool, ahora: float, paso_siguiente: str) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET consentimiento_aceptado = ?, paso = ?, actualizado_en = ? WHERE id = ?",
                (1 if aceptado else 0, paso_siguiente, ahora, pedido_id),
            ),
        )

    def fijar_entrega(
        self,
        pedido_id: int,
        tipo_entrega: str,
        ahora: float,
        paso_siguiente: str,
        zona_domicilio: str | None = None,
        direccion_texto: str | None = None,
        latitud: float | None = None,
        longitud: float | None = None,
    ) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                """
                UPDATE pedidos SET
                    tipo_entrega = ?,
                    zona_domicilio = ?,
                    direccion_texto = ?,
                    latitud = ?,
                    longitud = ?,
                    paso = ?,
                    actualizado_en = ?
                WHERE id = ?
                """,
                (tipo_entrega, zona_domicilio, direccion_texto, latitud, longitud, paso_siguiente, ahora, pedido_id),
            ),
        )

    def tocar(self, pedido_id: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET actualizado_en = ? WHERE id = ?",
                (ahora, pedido_id),
            ),
        )

    def confirmar(self, pedido_id: int, total: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET estado = ?, total = ?, actualizado_en = ? WHERE id = ?",
                (ESTADO_RECIBIDO, total, ahora, pedido_id),
            ),
        )

    def cancelar(self, pedido_id: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET estado = ?, actualizado_en = ? WHERE id = ?",
                (ESTADO_CANCELADO, ahora, pedido_id),
            ),
        )

    def confirmar_efectivo(self, pedido_id: int, total: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET estado = ?, total = ?, metodo_pago = 'efectivo', "
                "actualizado_en = ? WHERE id = ?",
                (ESTADO_RECIBIDO, total, ahora, pedido_id),
            ),
        )

    def marcar_pago_pendiente(self, pedido_id: int, total: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET estado = ?, total = ?, metodo_pago = 'qr', paso = ?, "
                "actualizado_en = ? WHERE id = ?",
                (ESTADO_PAGO_PENDIENTE, total, "pago_pendiente", ahora, pedido_id),
            ),
        )

    def marcar_pago_por_verificar(self, pedido_id: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET estado = ?, paso = ?, actualizado_en = ? WHERE id = ?",
                (ESTADO_PAGO_POR_VERIFICAR, "pago_por_verificar", ahora, pedido_id),
            ),
        )

    def marcar_pagado(self, pedido_id: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET estado = ?, actualizado_en = ? WHERE id = ?",
                (ESTADO_PAGADO, ahora, pedido_id),
            ),
        )

    def volver_a_pago_pendiente(self, pedido_id: int, ahora: float) -> None:
        ejecutar(
            self._ruta_bd,
            lambda conexion: conexion.execute(
                "UPDATE pedidos SET estado = ?, paso = ?, actualizado_en = ? WHERE id = ?",
                (ESTADO_PAGO_PENDIENTE, "pago_pendiente", ahora, pedido_id),
            ),
        )
