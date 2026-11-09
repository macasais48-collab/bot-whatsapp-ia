"""Secuencia completa de mensajes de un pedido real (recoger en el local +
pago en efectivo: la ruta más corta que pasa por "Pedido #N recibido"), lista
para enviar al webhook en la prueba de carga.

La cantidad de cada cliente varía según su índice, así que el total esperado
es distinto para cada uno — eso permite detectar de inmediato si un pedido se
mezclara con el de otro cliente (dos totales iguales no lo revelarían).
"""
from __future__ import annotations

import time
from collections.abc import Callable

PRECIO_TAMAL_SENCILLO = 8000


def cantidad_para(indice_cliente: int) -> int:
    return 2 + (indice_cliente % 5)  # 2..6 unidades, nunca toca el mínimo de domicilio (no aplica: es "recoger")


def total_esperado(indice_cliente: int) -> int:
    return cantidad_para(indice_cliente) * PRECIO_TAMAL_SENCILLO


def _payload_base(numero: str, id_mensaje: str, mensaje_extra: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "999"},
                            "messages": [
                                {
                                    "from": numero,
                                    "id": id_mensaje,
                                    "timestamp": str(int(time.time())),
                                    **mensaje_extra,
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _payload_lista(numero, id_mensaje, id_fila):
    return _payload_base(
        numero, id_mensaje,
        {"type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": id_fila, "title": "x", "description": ""}}},
    )


def _payload_texto(numero, id_mensaje, texto):
    return _payload_base(numero, id_mensaje, {"type": "text", "text": {"body": texto}})


def _payload_boton(numero, id_mensaje, id_boton):
    return _payload_base(
        numero, id_mensaje,
        {"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": id_boton, "title": "x"}}},
    )


def construir_pasos(numero: str, indice_cliente: int) -> list[tuple[str, Callable[[], dict]]]:
    """Devuelve [(nombre_del_paso, constructor_del_payload), ...] en orden. Cada
    constructor se llama justo antes de enviarse, para que el timestamp del
    mensaje sea siempre reciente (el webhook descarta mensajes de más de 5
    minutos de antigüedad)."""
    cantidad = cantidad_para(indice_cliente)
    prefijo_id = f"carga-{numero}"

    return [
        ("elegir_producto", lambda: _payload_lista(numero, f"{prefijo_id}-1", "tamal_sencillo")),
        ("elegir_cantidad", lambda: _payload_texto(numero, f"{prefijo_id}-2", str(cantidad))),
        ("continuar", lambda: _payload_boton(numero, f"{prefijo_id}-3", "continuar")),
        ("recoger_en_local", lambda: _payload_boton(numero, f"{prefijo_id}-4", "recoger_local")),
        ("confirmar", lambda: _payload_boton(numero, f"{prefijo_id}-5", "confirmar")),
        ("pagar_en_efectivo", lambda: _payload_boton(numero, f"{prefijo_id}-6", "pago_efectivo")),
    ]
