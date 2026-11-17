"""Agenda de citas (sub-fase 7a): validación de la configuración `citas` del
perfil y cálculo PURO de horarios (sin base de datos, sin red, reloj inyectado).

Todas las horas son de Bogotá (America/Bogota; Colombia no tiene horario de
verano). Un horario se identifica por su inicio en texto local ordenable,
"YYYY-MM-DD HH:MM", que es también lo que guarda la tabla `citas`.

Reglas (ver plan de la sub-fase 7a):
- Las horas empiezan cada `duracion_minutos` dentro de cada franja, y solo si
  la cita completa cabe antes del fin de la franja.
- Nunca se ofrece un horario pasado, antes de la anticipación mínima, fuera de
  la ventana de `dias_hacia_adelante`, en un día sin horario, bloqueado o
  festivo cerrado, ni con los cupos llenos.
"""
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import holidays

ZONA_BOGOTA = ZoneInfo("America/Bogota")
FORMATO_INICIO = "%Y-%m-%d %H:%M"
DIAS_SEMANA = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")

FESTIVOS_CERRADO = "cerrado"
FESTIVOS_ABIERTO = "abierto"

# Valores por defecto de los campos opcionales de `citas`.
POR_DEFECTO = {
    "cupos_por_horario": 1,
    "anticipacion_minima_minutos": 60,
    "dias_hacia_adelante": 14,
    "max_citas_por_cliente": 3,
    "retencion_dias": 30,
    "festivos": FESTIVOS_CERRADO,
}

# Rangos permitidos (mínimo, máximo) de los campos enteros.
RANGOS_ENTEROS = {
    "duracion_minutos": (5, 480),
    "cupos_por_horario": (1, 20),
    "anticipacion_minima_minutos": (0, 7 * 24 * 60),
    "dias_hacia_adelante": (1, 60),
    "max_citas_por_cliente": (1, 20),
    "retencion_dias": (1, 365),
}

MAXIMO_DATOS = 5
LIMITE_PREGUNTA_DATO = 300
LIMITE_ETIQUETA_DATO = 20
PATRON_CLAVE_DATO = re.compile(r"^[a-z_]{1,20}$")
PATRON_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
PATRON_TELEFONO = re.compile(r"^[0-9 +()-]{7,20}$")

CLAVES_PERMITIDAS = set(RANGOS_ENTEROS) | {
    "festivos", "dias_bloqueados", "horario", "datos", "telefono_negocio",
}


# -- Validación de la configuración --


def _error(nombre_archivo: str, mensaje: str) -> ValueError:
    return ValueError(f"{nombre_archivo}: {mensaje}")


def _minutos_desde_hora(texto, nombre_archivo: str, contexto: str) -> int:
    if not isinstance(texto, str):
        raise _error(nombre_archivo, f"{contexto} debe ser una hora 'HH:MM' (24 horas).")
    coincidencia = PATRON_HORA.match(texto)
    if coincidencia is None:
        raise _error(nombre_archivo, f"{contexto} debe ser una hora 'HH:MM' (24 horas), no '{texto}'.")
    return int(coincidencia.group(1)) * 60 + int(coincidencia.group(2))


def _validar_horario(horario, nombre_archivo: str) -> dict:
    if not isinstance(horario, dict) or not horario:
        raise _error(nombre_archivo, "'citas.horario' debe ser un objeto con al menos un día.")

    resultado = {}
    for nombre_dia, franjas in horario.items():
        if nombre_dia not in DIAS_SEMANA:
            raise _error(
                nombre_archivo,
                f"'citas.horario' tiene el día '{nombre_dia}'; use solo: {', '.join(DIAS_SEMANA)} "
                "(minúsculas, sin tilde).",
            )
        if not isinstance(franjas, list) or not franjas:
            raise _error(nombre_archivo, f"'citas.horario.{nombre_dia}' debe ser una lista de franjas.")

        franjas_minutos = []
        for indice, franja in enumerate(franjas):
            contexto = f"'citas.horario.{nombre_dia}[{indice}]'"
            if not isinstance(franja, list) or len(franja) != 2:
                raise _error(nombre_archivo, f"{contexto} debe ser [\"HH:MM\", \"HH:MM\"].")
            inicio = _minutos_desde_hora(franja[0], nombre_archivo, contexto)
            fin = _minutos_desde_hora(franja[1], nombre_archivo, contexto)
            if inicio >= fin:
                raise _error(nombre_archivo, f"{contexto}: la hora de inicio debe ser anterior a la de fin.")
            franjas_minutos.append((inicio, fin))

        franjas_minutos.sort()
        for (_, fin_anterior), (inicio_siguiente, _) in zip(franjas_minutos, franjas_minutos[1:]):
            if inicio_siguiente < fin_anterior:
                raise _error(nombre_archivo, f"'citas.horario.{nombre_dia}' tiene franjas que se cruzan.")
        resultado[DIAS_SEMANA.index(nombre_dia)] = franjas_minutos
    return resultado


def _validar_datos(datos, nombre_archivo: str) -> list:
    if not isinstance(datos, list) or not (1 <= len(datos) <= MAXIMO_DATOS):
        raise _error(nombre_archivo, f"'citas.datos' debe ser una lista de 1 a {MAXIMO_DATOS} datos a pedir.")

    resultado = []
    claves_vistas = set()
    for indice, dato in enumerate(datos):
        contexto = f"'citas.datos[{indice}]'"
        if not isinstance(dato, dict):
            raise _error(nombre_archivo, f"{contexto} debe ser un objeto.")
        clave = dato.get("clave")
        if not isinstance(clave, str) or not PATRON_CLAVE_DATO.match(clave):
            raise _error(
                nombre_archivo, f"{contexto}.clave debe tener 1 a 20 letras minúsculas o guion bajo."
            )
        if clave in claves_vistas:
            raise _error(nombre_archivo, f"'citas.datos' repite la clave '{clave}'.")
        claves_vistas.add(clave)
        pregunta = dato.get("pregunta")
        if not isinstance(pregunta, str) or not (1 <= len(pregunta.strip()) <= LIMITE_PREGUNTA_DATO):
            raise _error(nombre_archivo, f"{contexto}.pregunta debe tener 1 a {LIMITE_PREGUNTA_DATO} caracteres.")
        etiqueta = dato.get("etiqueta")
        if not isinstance(etiqueta, str) or not (1 <= len(etiqueta.strip()) <= LIMITE_ETIQUETA_DATO):
            raise _error(nombre_archivo, f"{contexto}.etiqueta debe tener 1 a {LIMITE_ETIQUETA_DATO} caracteres.")
        resultado.append({"clave": clave, "pregunta": pregunta.strip(), "etiqueta": etiqueta.strip()})
    return resultado


def validar_config_citas(citas, nombre_archivo: str) -> dict:
    """Valida la sección `citas` de un archivo de recursos y la devuelve
    normalizada (enteros con sus valores por defecto, horario por número de día
    0=lunes en minutos, días bloqueados como `date`). Falla con un ValueError
    claro, igual que el resto de recursos.py: mejor no arrancar que agendar mal."""
    if not isinstance(citas, dict):
        raise _error(nombre_archivo, "'citas' debe ser un objeto.")

    desconocidas = set(citas) - CLAVES_PERMITIDAS
    if desconocidas:
        raise _error(nombre_archivo, f"'citas' tiene claves no reconocidas: {', '.join(sorted(desconocidas))}.")

    for obligatoria in ("duracion_minutos", "horario", "datos"):
        if obligatoria not in citas:
            raise _error(nombre_archivo, f"'citas.{obligatoria}' es obligatorio.")

    resultado = {}
    for campo, (minimo, maximo) in RANGOS_ENTEROS.items():
        valor = citas.get(campo, POR_DEFECTO.get(campo))
        if isinstance(valor, bool) or not isinstance(valor, int) or not (minimo <= valor <= maximo):
            raise _error(nombre_archivo, f"'citas.{campo}' debe ser un número entero entre {minimo} y {maximo}.")
        resultado[campo] = valor

    festivos = citas.get("festivos", POR_DEFECTO["festivos"])
    if festivos not in (FESTIVOS_CERRADO, FESTIVOS_ABIERTO):
        raise _error(nombre_archivo, "'citas.festivos' debe ser \"cerrado\" o \"abierto\".")
    resultado["festivos"] = festivos

    bloqueados = citas.get("dias_bloqueados", [])
    if not isinstance(bloqueados, list):
        raise _error(nombre_archivo, "'citas.dias_bloqueados' debe ser una lista de fechas 'AAAA-MM-DD'.")
    fechas_bloqueadas = set()
    for valor in bloqueados:
        try:
            fechas_bloqueadas.add(date.fromisoformat(valor))
        except (TypeError, ValueError):
            raise _error(
                nombre_archivo, f"'citas.dias_bloqueados' tiene una fecha inválida: {valor!r} (use 'AAAA-MM-DD')."
            ) from None
    resultado["dias_bloqueados"] = frozenset(fechas_bloqueadas)

    resultado["horario"] = _validar_horario(citas["horario"], nombre_archivo)
    resultado["datos"] = _validar_datos(citas["datos"], nombre_archivo)

    telefono = citas.get("telefono_negocio")
    if telefono is not None and (not isinstance(telefono, str) or not PATRON_TELEFONO.match(telefono)):
        raise _error(
            nombre_archivo, "'citas.telefono_negocio' debe ser un teléfono de 7 a 20 caracteres (dígitos, espacios, +, guiones)."
        )
    resultado["telefono_negocio"] = telefono
    return resultado


# -- Cálculo de horarios (puro) --


def ahora_bogota(ahora: float) -> datetime:
    return datetime.fromtimestamp(ahora, ZONA_BOGOTA)


def texto_inicio(momento: datetime) -> str:
    return momento.strftime(FORMATO_INICIO)


def momento_desde_inicio(inicio: str) -> datetime:
    return datetime.strptime(inicio, FORMATO_INICIO).replace(tzinfo=ZONA_BOGOTA)


@lru_cache(maxsize=16)
def _festivos_del_anio(anio: int) -> frozenset:
    return frozenset(holidays.Colombia(years=anio))


def es_festivo(fecha: date) -> bool:
    return fecha in _festivos_del_anio(fecha.year)


def franjas_del_dia(config: dict, fecha: date) -> list[str]:
    """Todos los inicios posibles del día según el horario, sin mirar el reloj
    ni la ocupación. Vacío si ese día no se atiende, está bloqueado o es
    festivo cerrado."""
    if fecha in config["dias_bloqueados"]:
        return []
    if config["festivos"] == FESTIVOS_CERRADO and es_festivo(fecha):
        return []

    duracion = config["duracion_minutos"]
    medianoche = datetime(fecha.year, fecha.month, fecha.day, tzinfo=ZONA_BOGOTA)
    inicios = []
    for inicio_franja, fin_franja in config["horario"].get(fecha.weekday(), []):
        minuto = inicio_franja
        while minuto + duracion <= fin_franja:
            inicios.append(texto_inicio(medianoche + timedelta(minutes=minuto)))
            minuto += duracion
    return inicios


def ventana_de_fechas(config: dict, ahora: float) -> list[date]:
    """Hoy y los `dias_hacia_adelante` días siguientes (ambos extremos incluidos)."""
    hoy = ahora_bogota(ahora).date()
    return [hoy + timedelta(days=i) for i in range(config["dias_hacia_adelante"] + 1)]


def rango_de_consulta(config: dict, ahora: float) -> tuple[str, str]:
    """(desde, hasta) inclusivos para pedir la ocupación de toda la ventana en
    una sola consulta a la base."""
    fechas = ventana_de_fechas(config, ahora)
    return f"{fechas[0].isoformat()} 00:00", f"{fechas[-1].isoformat()} 23:59"


def _primer_inicio_permitido(config: dict, ahora: float) -> str:
    return texto_inicio(ahora_bogota(ahora) + timedelta(minutes=config["anticipacion_minima_minutos"]))


def horas_libres(config: dict, fecha: date, ahora: float, ocupacion: dict) -> list[str]:
    """Inicios ofrecibles de ese día: dentro de la ventana, no antes de la
    anticipación mínima y con cupo libre. `ocupacion` = {inicio: citas
    confirmadas}."""
    if fecha not in ventana_de_fechas(config, ahora):
        return []
    primer_permitido = _primer_inicio_permitido(config, ahora)
    cupos = config["cupos_por_horario"]
    return [
        inicio
        for inicio in franjas_del_dia(config, fecha)
        if inicio >= primer_permitido and ocupacion.get(inicio, 0) < cupos
    ]


def dias_disponibles(config: dict, ahora: float, ocupacion: dict) -> list[date]:
    """Días de la ventana con al menos una hora libre, en orden."""
    return [fecha for fecha in ventana_de_fechas(config, ahora) if horas_libres(config, fecha, ahora, ocupacion)]


def inicio_disponible(config: dict, inicio: str, ahora: float, ocupacion: dict) -> bool:
    """¿Se puede ofrecer/aceptar este inicio ahora mismo? Para filas de listas
    viejas: nunca se acepta un horario a ciegas, se recalcula."""
    try:
        fecha = momento_desde_inicio(inicio).date()
    except (TypeError, ValueError):
        return False
    return inicio in horas_libres(config, fecha, ahora, ocupacion)
