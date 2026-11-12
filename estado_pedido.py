"""Estados de ENTREGA de un pedido confirmado (sub-fase 5b).

Mismo patrón que pago_pedido.py: validar el estado actual → transicionar →
idempotencia (en el propio UPDATE de pedidos.avanzar_estado_entrega). Lo usan
el flujo del dueño en webhook.py (palabra "pedidos", lista, botón) y
gestionar_pedido.py (respaldo manual) — nunca la IA.

Transiciones (columna `estado_entrega`, aparte del estado de pago):
- Domicilio: en_preparacion → en_camino → entregado.
- Recoger:   en_preparacion → listo_para_recoger → entregado.
"""
import logging
import unicodedata

from pedido_resumen import entrega_una_linea, formatear_pesos, resumen_productos_una_linea
from pedidos import (
    ENTREGA_EN_CAMINO,
    ENTREGA_EN_PREPARACION,
    ENTREGA_ENTREGADO,
    ENTREGA_LISTO_PARA_RECOGER,
    Pedidos,
)
from telefono import enmascarar_numero

logger = logging.getLogger(__name__)

PALABRAS_CLAVE_PEDIDOS = {"pedidos"}

PREFIJO_BOTON_AVANZAR = "avanzar_"
PREFIJO_FILA_VER_PEDIDO = "ver_pedido_"
PREFIJO_FILA_PAGINA = "pedidos_pagina_"

# Límite oficial de Meta: una lista admite como máximo 10 filas en total. Con
# más de 10 pedidos activos se muestran 9 + una fila "Ver más".
MAXIMO_FILAS_LISTA = 10
PEDIDOS_POR_PAGINA_CON_VER_MAS = MAXIMO_FILAS_LISTA - 1

LISTA_TEXTO_CUERPO = (
    "Pedidos activos, del más antiguo al más reciente. Toque uno para avanzar su estado."
)
LISTA_TEXTO_BOTON = "Ver pedidos"
LISTA_TITULO_SECCION = "Pedidos activos"
MENSAJE_SIN_PEDIDOS_ACTIVOS = "No hay pedidos activos en este momento."

_SIGUIENTE_ESTADO = {
    ("domicilio", ENTREGA_EN_PREPARACION): ENTREGA_EN_CAMINO,
    ("domicilio", ENTREGA_EN_CAMINO): ENTREGA_ENTREGADO,
    ("recoger", ENTREGA_EN_PREPARACION): ENTREGA_LISTO_PARA_RECOGER,
    ("recoger", ENTREGA_LISTO_PARA_RECOGER): ENTREGA_ENTREGADO,
}

ETIQUETA_ESTADO = {
    ENTREGA_EN_PREPARACION: "En preparación",
    ENTREGA_EN_CAMINO: "En camino",
    ENTREGA_LISTO_PARA_RECOGER: "Listo para recoger",
    ENTREGA_ENTREGADO: "Entregado",
}

# Títulos de botón: máximo 20 caracteres (límite de Meta).
TITULO_BOTON_AVANZAR = {
    ENTREGA_EN_CAMINO: "Marcar en camino",
    ENTREGA_LISTO_PARA_RECOGER: "Listo para recoger",
    ENTREGA_ENTREGADO: "Marcar entregado",
}

MENSAJE_CLIENTE = {
    ENTREGA_EN_CAMINO: "Su pedido #{id} va en camino.",
    ENTREGA_LISTO_PARA_RECOGER: "Su pedido #{id} está listo para recoger.",
    ENTREGA_ENTREGADO: "Su pedido #{id} fue entregado. ¡Gracias por su compra!",
}


def es_palabra_clave_pedidos(texto: str | None) -> bool:
    if not texto:
        return False
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower() in PALABRAS_CLAVE_PEDIDOS


def _tipo_entrega(pedido: dict) -> str:
    return "domicilio" if pedido.get("tipo_entrega") == "domicilio" else "recoger"


def siguiente_estado(pedido: dict) -> str | None:
    return _SIGUIENTE_ESTADO.get((_tipo_entrega(pedido), pedido.get("estado_entrega")))


def id_boton_avanzar(pedido_id: int, estado_nuevo: str) -> str:
    return f"{PREFIJO_BOTON_AVANZAR}{pedido_id}_{estado_nuevo}"


def interpretar_boton_avanzar(id_boton: str) -> tuple[int, str] | None:
    """`avanzar_42_en_camino` → (42, "en_camino"). None si el id no es válido
    o el estado no es uno de los conocidos (un id manipulado nunca pasa)."""
    if not id_boton.startswith(PREFIJO_BOTON_AVANZAR):
        return None
    resto = id_boton[len(PREFIJO_BOTON_AVANZAR):]
    id_texto, _, estado_nuevo = resto.partition("_")
    if not id_texto.isdigit() or estado_nuevo not in TITULO_BOTON_AVANZAR:
        return None
    return int(id_texto), estado_nuevo


def interpretar_fila(id_fila: str) -> tuple[str, int] | None:
    """Fila de la lista del dueño: ("ver", id_pedido) o ("pagina", numero)."""
    for prefijo, tipo in ((PREFIJO_FILA_VER_PEDIDO, "ver"), (PREFIJO_FILA_PAGINA, "pagina")):
        if id_fila.startswith(prefijo):
            valor = id_fila[len(prefijo):]
            if valor.isdigit() and int(valor) >= 1:
                return tipo, int(valor)
    return None


def _descripcion_corta(pedido: dict) -> str:
    entrega = "Domicilio" if _tipo_entrega(pedido) == "domicilio" else "Recoger"
    estado = ETIQUETA_ESTADO.get(pedido.get("estado_entrega"), pedido.get("estado_entrega") or "—")
    total = formatear_pesos(pedido.get("total") or 0)
    return f"{entrega} · {estado} · {total}"


def pagina_de_pedidos_activos(pedidos: Pedidos, numero_pagina: int = 1) -> list[dict] | None:
    """Secciones listas para enviar_lista, o None si no hay pedidos activos en
    esa página. Con más de 10 pedidos restantes: 9 + fila "Ver más"; con 10 o
    menos, todos, sin fila de paginación."""
    desplazamiento = (numero_pagina - 1) * PEDIDOS_POR_PAGINA_CON_VER_MAS
    restantes = pedidos.listar_activos_entrega(desplazamiento, MAXIMO_FILAS_LISTA + 1)
    if not restantes:
        return None

    hay_mas = len(restantes) > MAXIMO_FILAS_LISTA
    visibles = restantes[:PEDIDOS_POR_PAGINA_CON_VER_MAS] if hay_mas else restantes
    # Sin teléfono ni dirección en la lista: solo número, entrega, estado y total.
    filas = [
        {
            "id": f'{PREFIJO_FILA_VER_PEDIDO}{pedido["id"]}',
            "titulo": f'Pedido #{pedido["id"]}',
            "descripcion": _descripcion_corta(pedido),
        }
        for pedido in visibles
    ]
    if hay_mas:
        filas.append(
            {
                "id": f"{PREFIJO_FILA_PAGINA}{numero_pagina + 1}",
                "titulo": "Ver más",
                "descripcion": "Siguientes pedidos activos",
            }
        )
    return [{"titulo": LISTA_TITULO_SECCION, "filas": filas}]


def detalle_para_dueno(pedido: dict, domicilio: dict) -> tuple[str, list[dict]]:
    """Texto del pedido + el ÚNICO botón del siguiente paso válido (lista vacía
    si ya no hay siguiente paso, p. ej. ya entregado)."""
    try:
        entrega = entrega_una_linea(pedido, domicilio)
    except KeyError:
        # Zona que ya no existe en los recursos del perfil: se muestra sin ella.
        entrega = "Domicilio" if _tipo_entrega(pedido) == "domicilio" else "Recoger en el local"
    estado = ETIQUETA_ESTADO.get(pedido.get("estado_entrega"), pedido.get("estado_entrega") or "—")
    texto = (
        f'Pedido #{pedido["id"]}\n'
        f"Productos: {resumen_productos_una_linea(pedido)}\n"
        f'Total: {formatear_pesos(pedido.get("total") or 0)}\n'
        f"Entrega: {entrega}\n"
        f"Estado: {estado}"
    )
    estado_nuevo = siguiente_estado(pedido)
    if estado_nuevo is None:
        return texto, []
    return texto, [{"id": id_boton_avanzar(pedido["id"], estado_nuevo), "titulo": TITULO_BOTON_AVANZAR[estado_nuevo]}]


def avanzar_estado(
    pedidos: Pedidos,
    pedido_id: int,
    estado_nuevo: str,
    ahora: float,
    enviar_texto_con_wamid_fn,
) -> str:
    """Aplica la transición solo si `estado_nuevo` es justo el siguiente paso
    del estado actual del pedido; avisa al cliente en texto libre y devuelve
    el mensaje de resultado para el dueño (o para la consola)."""
    pedido = pedidos.obtener(pedido_id)
    if pedido is None:
        return f"No existe un pedido con el número {pedido_id}."
    if pedido.get("estado_entrega") is None:
        return f"El pedido #{pedido_id} todavía no está confirmado; no tiene estado de entrega."

    estado_actual = pedido["estado_entrega"]
    if siguiente_estado(pedido) != estado_nuevo:
        etiqueta = ETIQUETA_ESTADO.get(estado_actual, estado_actual)
        return f"El pedido #{pedido_id} ya no está en ese paso (estado actual: {etiqueta}). No se hizo ningún cambio."

    if not pedidos.avanzar_estado_entrega(pedido_id, estado_actual, estado_nuevo, ahora):
        # Otra pulsación lo cambió entre la lectura y el UPDATE.
        return f"El pedido #{pedido_id} ya había cambiado de estado. No se hizo ningún cambio."

    numero_enmascarado = enmascarar_numero(pedido["numero_cliente"])
    logger.info(
        "Pedido #%s: estado de entrega %s -> %s (cliente=%s)",
        pedido_id, estado_actual, estado_nuevo, numero_enmascarado,
    )

    ok, wamid = enviar_texto_con_wamid_fn(pedido["numero_cliente"], MENSAJE_CLIENTE[estado_nuevo].format(id=pedido_id))
    if ok and wamid:
        # Un fallo posterior (status "failed", p. ej. 131047 por la ventana de
        # 24 horas) se asocia a este pedido en webhook._procesar_estado.
        pedidos.registrar_wamid_aviso_dueno(wamid, pedido_id, "estado_cliente", ahora)
    if not ok:
        # El estado ya quedó aplicado: el flujo sigue, solo se informa.
        logger.info(
            "Pedido #%s: no se pudo enviar el aviso de estado al cliente (cliente=%s).",
            pedido_id, numero_enmascarado,
        )
        return f"Pedido #{pedido_id}: {ETIQUETA_ESTADO[estado_nuevo]}. No se pudo avisar al cliente."
    return f"Pedido #{pedido_id}: {ETIQUETA_ESTADO[estado_nuevo]}. Se avisó al cliente."
