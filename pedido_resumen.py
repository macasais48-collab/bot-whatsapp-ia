"""Resumen de un pedido: la versión multilínea de siempre (para mensajes libres
al cliente/dueño) y las versiones compactas en una sola línea, saneadas para
variables de plantilla de WhatsApp (Meta no permite saltos de línea,
tabulaciones ni más de cuatro espacios seguidos en una variable).

Sin dependencias de flujo_pedido.py ni pago_pedido.py: lo usan los dos, sin
import circular (flujo_pedido.py ya importa de pago_pedido.py)."""
import re

LIMITE_UNA_LINEA_POR_DEFECTO = 200

_ESPACIOS_PROHIBIDOS = re.compile(r"[\r\n\t]+| {4,}")


def formatear_pesos(valor: int) -> str:
    return f"${valor:,}".replace(",", ".")


def _una_linea(texto: str, limite: int) -> str:
    saneado = _ESPACIOS_PROHIBIDOS.sub(" ", texto).strip()
    if len(saneado) <= limite:
        return saneado
    return saneado[: limite - 1].rstrip() + "…"


def construir_resumen(pedido: dict, domicilio: dict) -> tuple[str, int]:
    lineas = ["Resumen de su pedido:"]
    total = 0
    for item in pedido["items"]:
        lineas.append(f'- {item["cantidad"]} x {item["nombre"]}: {formatear_pesos(item["subtotal"])}')
        total += item["subtotal"]

    tipo_entrega = pedido["tipo_entrega"]
    zona_domicilio = pedido["zona_domicilio"]
    if tipo_entrega == "domicilio" and zona_domicilio is not None:
        nombre_zona = domicilio[zona_domicilio]["nombre"]
        costo_domicilio = domicilio[zona_domicilio]["costo"]
        lineas.append(f"Entrega: Domicilio - {nombre_zona}")
        if pedido.get("direccion_texto"):
            lineas.append(f"Dirección: {pedido['direccion_texto']}")
        elif pedido.get("latitud") is not None:
            lineas.append("Dirección: ubicación compartida por WhatsApp")
        lineas.append(f"Costo de domicilio: {formatear_pesos(costo_domicilio)}")
        total += costo_domicilio
    else:
        lineas.append("Entrega: Recoger en el local.")

    lineas.append(f"Total: {formatear_pesos(total)}")
    return "\n".join(lineas), total


def resumen_productos_una_linea(pedido: dict, limite: int = LIMITE_UNA_LINEA_POR_DEFECTO) -> str:
    texto = ", ".join(f'{item["cantidad"]} x {item["nombre"]}' for item in pedido["items"])
    return _una_linea(texto, limite)


def entrega_una_linea(pedido: dict, domicilio: dict, limite: int = LIMITE_UNA_LINEA_POR_DEFECTO) -> str:
    tipo_entrega = pedido["tipo_entrega"]
    zona_domicilio = pedido["zona_domicilio"]
    if tipo_entrega != "domicilio" or zona_domicilio is None:
        return "Recoger en el local"

    nombre_zona = domicilio[zona_domicilio]["nombre"]
    if pedido.get("direccion_texto"):
        direccion = pedido["direccion_texto"]
    elif pedido.get("latitud") is not None:
        direccion = "ubicación compartida por WhatsApp"
    else:
        direccion = ""
    texto = f"Domicilio - {nombre_zona}, {direccion}" if direccion else f"Domicilio - {nombre_zona}"
    return _una_linea(texto, limite)
