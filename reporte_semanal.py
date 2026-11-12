"""Reporte semanal al negocio (sub-fase 5c).

Cifras agregadas de una semana (lunes 00:00 a domingo 23:59, hora de Bogotá):
pedidos confirmados, ventas, desglose por método de pago y forma de entrega,
los 3 productos más vendidos y entregados vs. pendientes. Nunca teléfonos,
nombres ni direcciones: pedidos.datos_para_reporte ni siquiera los consulta.

Dos caminos:
- El dueño escribe "reporte" → semana EN CURSO, en texto libre (su ventana de
  24 horas está abierta: acaba de escribir).
- Envío automático (APScheduler) el día/hora configurados → la última semana
  COMPLETA (la anterior), por plantilla si está configurada; si no, texto
  libre (solo llega con la ventana abierta). Una fila por semana en
  `reportes_enviados` evita enviar dos veces la misma semana.
"""
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from estado_pedido import normalizar_palabra
from pedido_resumen import formatear_pesos, una_linea
from pedidos import ENTREGA_ENTREGADO, Pedidos

logger = logging.getLogger(__name__)

ZONA_BOGOTA = ZoneInfo("America/Bogota")

PALABRAS_CLAVE_REPORTE = {"reporte"}

DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
}
DIA_POR_DEFECTO = 0  # lunes
HORA_POR_DEFECTO = 8
MINUTO_POR_DEFECTO = 0

MAXIMO_PRODUCTOS = 3
_PATRON_HORA = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")

_ETIQUETA_METODO = {"efectivo": "Efectivo", "qr": "QR / transferencia"}
_ETIQUETA_ENTREGA = {"domicilio": "Domicilio", "recoger": "Recoger en el local"}


def es_palabra_clave_reporte(texto: str | None) -> bool:
    return normalizar_palabra(texto) in PALABRAS_CLAVE_REPORTE


# -- Fechas --


def _inicio_semana(ahora: float) -> datetime:
    local = datetime.fromtimestamp(ahora, ZONA_BOGOTA)
    lunes = local - timedelta(days=local.weekday())
    return lunes.replace(hour=0, minute=0, second=0, microsecond=0)


def _fecha(momento: datetime) -> str:
    return momento.strftime("%d/%m/%Y")


def semana_anterior(ahora: float) -> tuple[float, float, str, str]:
    """(desde, hasta_exclusivo, clave ISO "2026-W45", etiqueta "dd/mm/aaaa al dd/mm/aaaa")."""
    inicio_actual = _inicio_semana(ahora)
    inicio_anterior = inicio_actual - timedelta(days=7)
    iso = inicio_anterior.isocalendar()
    clave = f"{iso.year}-W{iso.week:02d}"
    etiqueta = f"{_fecha(inicio_anterior)} al {_fecha(inicio_actual - timedelta(days=1))}"
    return inicio_anterior.timestamp(), inicio_actual.timestamp(), clave, etiqueta


def leer_programacion(dia_texto: str | None, hora_texto: str | None) -> tuple[int, int, int]:
    """REPORTE_SEMANAL_DIA ("lunes".."domingo", sin importar mayúsculas ni
    tildes) y REPORTE_SEMANAL_HORA ("8" o "08:30", 24 horas, hora de Bogotá).
    Vacías = lunes 8:00. Un valor inválido no impide arrancar el bot: se
    registra una advertencia y se usa el valor por defecto."""
    dia = DIA_POR_DEFECTO
    if dia_texto and dia_texto.strip():
        normalizado = normalizar_palabra(dia_texto)
        if normalizado in DIAS_SEMANA:
            dia = DIAS_SEMANA[normalizado]
        else:
            logger.warning("REPORTE_SEMANAL_DIA no es un día válido (lunes a domingo); se usa lunes.")

    hora, minuto = HORA_POR_DEFECTO, MINUTO_POR_DEFECTO
    if hora_texto and hora_texto.strip():
        coincidencia = _PATRON_HORA.match(hora_texto.strip())
        hora_leida = int(coincidencia.group(1)) if coincidencia else -1
        minuto_leido = int(coincidencia.group(2) or 0) if coincidencia else -1
        if 0 <= hora_leida <= 23 and 0 <= minuto_leido <= 59:
            hora, minuto = hora_leida, minuto_leido
        else:
            logger.warning("REPORTE_SEMANAL_HORA no es una hora válida (ej. 8 u 08:30); se usa 8:00.")
    return dia, hora, minuto


def momento_programado_esta_semana(ahora: float, dia: int, hora: int, minuto: int) -> float:
    return (_inicio_semana(ahora) + timedelta(days=dia, hours=hora, minutes=minuto)).timestamp()


# -- Cálculo --


def calcular_reporte(pedidos: Pedidos, desde: float, hasta: float) -> dict:
    datos = pedidos.datos_para_reporte(desde, hasta)
    filas = datos["pedidos"]

    por_metodo: dict[str, dict] = {}
    por_entrega: dict[str, int] = {}
    entregados = 0
    for fila in filas:
        metodo = fila["metodo_pago"] or "sin_especificar"
        resumen_metodo = por_metodo.setdefault(metodo, {"pedidos": 0, "ventas": 0})
        resumen_metodo["pedidos"] += 1
        resumen_metodo["ventas"] += fila["total"] or 0
        entrega = "domicilio" if fila["tipo_entrega"] == "domicilio" else "recoger"
        por_entrega[entrega] = por_entrega.get(entrega, 0) + 1
        if fila["estado_entrega"] == ENTREGA_ENTREGADO:
            entregados += 1

    return {
        "pedidos": len(filas),
        "ventas": sum(fila["total"] or 0 for fila in filas),
        "por_metodo": por_metodo,
        "por_entrega": por_entrega,
        "productos_top": datos["productos"][:MAXIMO_PRODUCTOS],
        "entregados": entregados,
        "pendientes": len(filas) - entregados,
    }


def _plural(cantidad: int, singular: str, plural: str) -> str:
    return f"{cantidad} {singular if cantidad == 1 else plural}"


def _linea_metodos(reporte: dict) -> str:
    partes = [
        f'{_ETIQUETA_METODO.get(metodo, "Sin especificar")} {valores["pedidos"]} ({formatear_pesos(valores["ventas"])})'
        for metodo, valores in sorted(reporte["por_metodo"].items())
    ]
    return ", ".join(partes) or "ninguno"


def _linea_entregas(reporte: dict) -> str:
    partes = [
        f"{_ETIQUETA_ENTREGA[tipo]} {cantidad}"
        for tipo, cantidad in sorted(reporte["por_entrega"].items())
    ]
    return ", ".join(partes) or "ninguno"


def _linea_productos(reporte: dict) -> str:
    return ", ".join(f"{cantidad} x {nombre}" for nombre, cantidad in reporte["productos_top"]) or "ninguno"


def _linea_estado_entregas(reporte: dict) -> str:
    return (
        f'{_plural(reporte["entregados"], "entregado", "entregados")} y '
        f'{_plural(reporte["pendientes"], "pendiente", "pendientes")}'
    )


def texto_reporte(reporte: dict, titulo: str) -> str:
    return "\n".join(
        [
            titulo,
            f'Pedidos confirmados: {reporte["pedidos"]}',
            f'Ventas totales: {formatear_pesos(reporte["ventas"])}',
            f"Por método de pago: {_linea_metodos(reporte)}",
            f"Por forma de entrega: {_linea_entregas(reporte)}",
            f"Productos más vendidos: {_linea_productos(reporte)}",
            f"Entregas: {_linea_estado_entregas(reporte)}",
        ]
    )


def variables_plantilla(reporte: dict, etiqueta_semana: str) -> list[str]:
    """Las 7 variables de docs/plantilla_reporte_semanal.md, en orden, cada una
    en una sola línea (regla de Meta) y nunca vacía."""
    return [
        una_linea(etiqueta_semana),
        str(reporte["pedidos"]),
        formatear_pesos(reporte["ventas"]),
        una_linea(_linea_metodos(reporte)),
        una_linea(_linea_entregas(reporte)),
        una_linea(_linea_productos(reporte)),
        una_linea(_linea_estado_entregas(reporte)),
    ]


def texto_semana_en_curso(pedidos: Pedidos, ahora: float) -> str:
    inicio = _inicio_semana(ahora)
    reporte = calcular_reporte(pedidos, inicio.timestamp(), ahora + 1)
    return texto_reporte(reporte, f"Reporte de la semana en curso (desde el lunes {_fecha(inicio)})")


# -- Envío automático --


def enviar_reporte_semana_anterior(
    pedidos: Pedidos,
    numero_dueno: str | None,
    ahora: float,
    enviar_texto_con_wamid_fn,
    enviar_plantilla_fn=None,
    plantilla_nombre: str | None = None,
    plantilla_idioma: str | None = None,
) -> bool:
    """Envía el reporte de la última semana completa, una sola vez por semana.
    Devuelve True solo si se envió en esta llamada."""
    if not numero_dueno:
        return False
    desde, hasta, clave, etiqueta = semana_anterior(ahora)
    if not pedidos.reservar_reporte(clave, ahora):
        logger.info("Reporte semanal %s ya enviado; no se repite.", clave)
        return False

    reporte = calcular_reporte(pedidos, desde, hasta)
    if plantilla_nombre and plantilla_idioma and enviar_plantilla_fn is not None:
        ok, wamid = enviar_plantilla_fn(
            numero_dueno, plantilla_nombre, plantilla_idioma, variables_plantilla(reporte, etiqueta)
        )
    else:
        ok, wamid = enviar_texto_con_wamid_fn(
            numero_dueno, texto_reporte(reporte, f"Reporte semanal del {etiqueta}")
        )

    if not ok:
        pedidos.liberar_reporte(clave)
        logger.warning("No se pudo enviar el reporte semanal %s; se reintentará.", clave)
        return False
    if wamid:
        # Un "failed" posterior se asocia a esta semana en webhook._procesar_estado.
        pedidos.fijar_wamid_reporte(clave, wamid)
    logger.info("Reporte semanal %s enviado al dueño (%d pedidos).", clave, reporte["pedidos"])
    return True


def recuperar_reporte_pendiente(
    pedidos: Pedidos, ahora: float, dia: int, hora: int, minuto: int, **envio
) -> bool:
    """Al arrancar: si ya pasó el momento programado de esta semana y el
    reporte de la semana anterior no se envió (el bot estaba apagado), se
    envía ahora. Antes de ese momento no hace nada: lo enviará el programador."""
    if ahora < momento_programado_esta_semana(ahora, dia, hora, minuto):
        return False
    _, _, clave, _ = semana_anterior(ahora)
    if pedidos.reporte_enviado(clave):
        return False
    logger.info("Reporte semanal %s pendiente al arrancar; se envía ahora.", clave)
    return enviar_reporte_semana_anterior(pedidos, ahora=ahora, **envio)


def iniciar_programador(tarea_semanal, tarea_recuperacion, dia: int, hora: int, minuto: int):
    """Programa `tarea_semanal` cada semana (día/hora de Bogotá) y ejecuta
    `tarea_recuperacion` una vez, de inmediato, en segundo plano.

    Se arranca desde gunicorn.conf.py (post_worker_init), una vez por worker.
    Hoy gunicorn corre con --workers 1, así que hay un solo programador. Si
    algún día se suben los workers, cada uno tendría su propio programador,
    pero el reporte igual sale una sola vez por semana: la reserva en
    `reportes_enviados` (clave primaria por semana) es atómica en SQLite."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    programador = BackgroundScheduler(timezone=ZONA_BOGOTA)
    programador.add_job(
        tarea_semanal,
        CronTrigger(day_of_week=dia, hour=hora, minute=minuto, timezone=ZONA_BOGOTA),
        id="reporte_semanal",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    # Sin trigger = una sola ejecución inmediata (recuperación al arrancar).
    programador.add_job(tarea_recuperacion, id="reporte_semanal_recuperacion")
    programador.start()
    return programador
