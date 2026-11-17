"""Flujo de agendamiento de citas del cliente (sub-fase 7a.2).

Pasos (columna `paso` de la tabla `citas`):
  dia → hora → consentimiento → dato:<clave> (uno por mensaje) → confirmacion

- Los días y las horas los arma SIEMPRE el código (agenda.py) a partir de la
  configuración del perfil y de la ocupación real; la IA nunca ve ni dice
  horarios: solo adjunta la agenda (`{"tipo": "agenda"}`).
- Una fila de una lista vieja nunca se acepta a ciegas: se recalcula si ese
  día/hora sigue disponible.
- El cupo se reserva al confirmar, en una sola sentencia atómica
  (`Citas.confirmar`), que también verifica el tope de citas por cliente.
- Consentimiento (Ley 1581) con botones [Acepto]/[No acepto] antes de pedir
  cualquier dato; la aceptación queda con fecha y hora en la cita. Si no
  acepta: no se agenda, se le da el teléfono del negocio y se deriva.
- "cancelar"/"asesor" y 30 minutos sin respuesta funcionan igual que en el
  flujo de pedido; la derivación avisa al dueño (sub-fases 6a/6b).
- Aviso de cita nueva al dueño: plantilla `aviso_cita_nueva` si está
  configurada, si no texto libre; wamid guardado para asociar un "failed".

Nunca registra en el log teléfonos completos ni datos de la cita.
"""
import logging
import time
from datetime import date

import agenda
import derivacion
from citas import (
    ESTADO_CONFIRMADA,
    RESULTADO_CONFIRMADA,
    RESULTADO_CUPO_LLENO,
    RESULTADO_TOPE_CLIENTE,
    Citas,
)
from flujo_pedido import PALABRAS_CLAVE_CANCELAR, PALABRAS_CLAVE_PERSONA, SEGUNDOS_TIMEOUT_PEDIDO, _normalizar
from pedido_resumen import una_linea
from pedidos import Pedidos
from telefono import enmascarar_numero

logger = logging.getLogger(__name__)

SEGUNDOS_TIMEOUT_CITA = SEGUNDOS_TIMEOUT_PEDIDO
LIMITE_DATO = 100
LIMITE_DATOS_AVISO = 300
MAXIMO_FILAS_LISTA = 10

# Ids de botones y filas (todas empiezan por "cita_": así las reconoce el webhook).
PREFIJO = "cita_"
ID_BOTON_AGENDAR = "agendar_cita"  # botón de bienvenida opcional del perfil
PREFIJO_FILA_DIA = "cita_dia_"  # cita_dia_2026-11-24
PREFIJO_FILA_HORA = "cita_hora_"  # cita_hora_2026-11-24_08:00
PREFIJO_FILA_MAS_DIAS = "cita_dias_pag_"  # cita_dias_pag_2
PREFIJO_FILA_MAS_HORAS = "cita_horas_pag_"  # cita_horas_pag_2026-11-24_2
ID_FILA_OTRO_DIA = "cita_otro_dia"
ID_BOTON_ACEPTO = "cita_acepto"
ID_BOTON_NO_ACEPTO = "cita_no_acepto"
ID_BOTON_CONFIRMAR = "cita_confirmar"
ID_BOTON_CAMBIAR = "cita_cambiar"
ID_BOTON_CANCELAR = "cita_cancelar"

PASO_DIA = "dia"
PASO_HORA = "hora"
PASO_CONSENTIMIENTO = "consentimiento"
PREFIJO_PASO_DATO = "dato:"
PASO_CONFIRMACION = "confirmacion"

DIAS_CORTOS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
DIAS_LARGOS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")

TEXTO_LISTA_DIAS = "Elija el día para su cita:"
TEXTO_BOTON_DIAS = "Ver días"
TEXTO_LISTA_HORAS = "Elija la hora para el {dia}:"
TEXTO_BOTON_HORAS = "Ver horas"
MENSAJE_SIN_DISPONIBILIDAD = (
    "Por ahora no tenemos horarios disponibles para agendar por este medio. "
    "Escriba *asesor* si desea que una persona del equipo le ayude."
)
MENSAJE_HORARIO_NO_DISPONIBLE = "Ese horario ya no está disponible. Estos siguen libres:"
MENSAJE_DIA_NO_DISPONIBLE = "Ese día ya no tiene horarios disponibles. Elija otro:"
MENSAJE_HORARIO_OCUPADO_AL_CONFIRMAR = "Ese horario acaba de ocuparse. Estos siguen libres:"
TEXTO_CONSENTIMIENTO = (
    "Para agendar su cita necesito algunos datos. Se usarán solo para gestionar su cita, "
    "conforme a la Ley 1581 de 2012, y puede pedir que se eliminen cuando quiera. "
    "¿Autoriza el tratamiento de estos datos?"
)
MENSAJE_NO_ACEPTA = "Entendido, sin su autorización no podemos agendar la cita por este medio."
MENSAJE_NO_ACEPTA_TELEFONO = " Puede llamarnos al {telefono}."
MENSAJE_CITA_CANCELADA = "Su solicitud de cita fue cancelada. Escríbame cuando quiera agendar de nuevo."
MENSAJE_CANCELADA_POR_INACTIVIDAD = (
    "Como pasaron más de 30 minutos sin respuesta, cancelé la solicitud de cita. "
    "Escríbame cuando quiera agendar de nuevo."
)
MENSAJE_TOPE = (
    "Ya tiene {maximo} citas agendadas con nosotros, el máximo por este medio. "
    "Si necesita otra, escriba *asesor* y una persona del equipo le ayudará."
)
MENSAJE_ENTRADA_NO_RECONOCIDA = (
    "No entendí esa respuesta. Para seguir con su cita, elija una de las opciones. "
    "Si desea cancelar, escriba *cancelar*."
)
MENSAJE_DATO_INVALIDO = "Por favor responda con un texto. {pregunta}"
MENSAJE_CITA_CONFIRMADA = (
    "¡Listo! Su cita #{id} quedó agendada para el {fecha_hora}.\n{datos}\n"
    "Si necesita cambiarla o cancelarla, escriba *asesor* y una persona del equipo le ayudará."
)


# -- Formato (puro) --


def hora_legible(inicio: str) -> str:
    momento = agenda.momento_desde_inicio(inicio)
    sufijo = "a.m." if momento.hour < 12 else "p.m."
    hora_12 = momento.hour % 12 or 12
    return f"{hora_12}:{momento.minute:02d} {sufijo}"


def dia_corto(fecha: date) -> str:
    return f"{DIAS_CORTOS[fecha.weekday()]} {fecha.day} {MESES[fecha.month - 1][:3]}"


def dia_largo(fecha: date) -> str:
    return f"{DIAS_LARGOS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"


def fecha_hora_legible(inicio: str) -> str:
    return f"{dia_largo(agenda.momento_desde_inicio(inicio).date())}, {hora_legible(inicio)}"


def datos_multilinea(config: dict, datos: dict) -> str:
    return "\n".join(
        f'{dato["etiqueta"]}: {datos[dato["clave"]]}' for dato in config["datos"] if dato["clave"] in datos
    )


def datos_una_linea(config: dict, datos: dict) -> str:
    texto = "; ".join(
        f'{dato["etiqueta"]}: {datos[dato["clave"]]}' for dato in config["datos"] if dato["clave"] in datos
    )
    return una_linea(texto, LIMITE_DATOS_AVISO) or "Sin datos"


def es_id_de_cita(id_interactivo: str | None) -> bool:
    return bool(id_interactivo) and id_interactivo.startswith(PREFIJO)


def _id_interactivo(mensaje: dict) -> str | None:
    if mensaje.get("type") != "interactive":
        return None
    interactivo = mensaje.get("interactive", {})
    if interactivo.get("type") == "button_reply":
        return interactivo.get("button_reply", {}).get("id")
    if interactivo.get("type") == "list_reply":
        return interactivo.get("list_reply", {}).get("id")
    return None


def _paginar(filas: list[dict], numero_pagina: int, fila_mas, filas_fijas: list[dict]) -> list[dict]:
    """Hasta 10 filas en total (límite de Meta): las `filas_fijas` al final y,
    si no caben todas, una fila "Ver más" (`fila_mas(siguiente_pagina)`)."""
    espacio = MAXIMO_FILAS_LISTA - len(filas_fijas)
    if len(filas) <= espacio and numero_pagina == 1:
        return filas + filas_fijas
    por_pagina = espacio - 1
    inicio = (numero_pagina - 1) * por_pagina
    visibles = filas[inicio:inicio + por_pagina]
    resultado = list(visibles)
    if inicio + por_pagina < len(filas):
        resultado.append(fila_mas(numero_pagina + 1))
    return resultado + filas_fijas


class FlujoCita:
    def __init__(
        self,
        citas: Citas,
        pedidos: Pedidos,
        config: dict,
        perfil: str,
        mensaje_derivacion: str,
        enviar_texto_fn,
        enviar_botones_fn,
        enviar_lista_fn,
        enviar_texto_con_wamid_fn,
        reloj=time.time,
        numero_dueno: str | None = None,
        enviar_plantilla_fn=None,
        plantilla_aviso_cita_nombre: str | None = None,
        plantilla_aviso_cita_idioma: str | None = None,
        plantilla_aviso_derivacion_nombre: str | None = None,
        plantilla_aviso_derivacion_idioma: str | None = None,
    ) -> None:
        self._citas = citas
        self._pedidos = pedidos
        self._config = config
        self._perfil = perfil
        self._mensaje_derivacion = mensaje_derivacion
        self._enviar_texto = enviar_texto_fn
        self._enviar_botones_fn = enviar_botones_fn
        self._enviar_lista_fn = enviar_lista_fn
        self._enviar_texto_con_wamid_fn = enviar_texto_con_wamid_fn
        self._reloj = reloj
        self._numero_dueno = numero_dueno
        self._enviar_plantilla_fn = enviar_plantilla_fn
        self._plantilla_aviso_cita_nombre = plantilla_aviso_cita_nombre
        self._plantilla_aviso_cita_idioma = plantilla_aviso_cita_idioma
        self._plantilla_aviso_derivacion_nombre = plantilla_aviso_derivacion_nombre
        self._plantilla_aviso_derivacion_idioma = plantilla_aviso_derivacion_idioma

    # -- Consultas para el webhook --

    def tiene_cita_en_construccion(self, numero: str) -> bool:
        return self._citas.obtener_en_construccion(numero) is not None

    # -- Disponibilidad --

    def _ocupacion(self, ahora: float) -> dict:
        desde, hasta = agenda.rango_de_consulta(self._config, ahora)
        return self._citas.ocupacion(self._perfil, desde, hasta)

    def _enviar_botones(self, numero: str, cuerpo: str, botones: list[tuple[str, str]]) -> None:
        self._enviar_botones_fn(numero, cuerpo, [{"id": id_, "titulo": titulo} for id_, titulo in botones])

    def ofrecer_dias(self, numero: str, cuerpo: str | None = None, numero_pagina: int = 1) -> bool:
        """Envía la lista de días con horas libres. Devuelve False (y avisa al
        cliente) si no hay ninguno."""
        ahora = self._reloj()
        ocupacion = self._ocupacion(ahora)
        dias = agenda.dias_disponibles(self._config, ahora, ocupacion)
        if not dias:
            self._enviar_texto(numero, MENSAJE_SIN_DISPONIBILIDAD)
            return False
        filas = []
        for fecha in dias:
            libres = len(agenda.horas_libres(self._config, fecha, ahora, ocupacion))
            filas.append({
                "id": f"{PREFIJO_FILA_DIA}{fecha.isoformat()}",
                "titulo": dia_corto(fecha),
                "descripcion": "1 horario libre" if libres == 1 else f"{libres} horarios libres",
            })
        filas = _paginar(
            filas, numero_pagina,
            lambda siguiente: {"id": f"{PREFIJO_FILA_MAS_DIAS}{siguiente}", "titulo": "Ver más días", "descripcion": ""},
            [],
        )
        self._enviar_lista_fn(numero, cuerpo or TEXTO_LISTA_DIAS, TEXTO_BOTON_DIAS, [{"titulo": "Días", "filas": filas}])
        return True

    def _ofrecer_horas(self, numero: str, fecha: date, cuerpo: str | None = None, numero_pagina: int = 1) -> bool:
        ahora = self._reloj()
        ocupacion = self._ocupacion(ahora)
        libres = agenda.horas_libres(self._config, fecha, ahora, ocupacion)
        if not libres:
            return False
        cupos = self._config["cupos_por_horario"]
        filas = [
            {
                "id": f"{PREFIJO_FILA_HORA}{inicio.replace(' ', '_')}",
                "titulo": hora_legible(inicio),
                "descripcion": (
                    f"Quedan {cupos - ocupacion.get(inicio, 0)} cupos"
                    if cupos > 1 and cupos - ocupacion.get(inicio, 0) > 1 else ""
                ),
            }
            for inicio in libres
        ]
        filas = _paginar(
            filas, numero_pagina,
            lambda siguiente: {
                "id": f"{PREFIJO_FILA_MAS_HORAS}{fecha.isoformat()}_{siguiente}", "titulo": "Ver más horas", "descripcion": "",
            },
            [{"id": ID_FILA_OTRO_DIA, "titulo": "Elegir otro día", "descripcion": ""}],
        )
        texto = cuerpo or TEXTO_LISTA_HORAS.format(dia=dia_largo(fecha))
        self._enviar_lista_fn(numero, texto, TEXTO_BOTON_HORAS, [{"titulo": "Horas", "filas": filas}])
        return True

    # -- Entrada principal --

    def manejar_mensaje(self, numero: str, mensaje: dict) -> None:
        ahora = self._reloj()
        cita = self._citas.obtener_en_construccion(numero)
        id_interactivo = _id_interactivo(mensaje)

        if cita is None:
            # Sin cita en construcción solo se acepta empezar desde una fila de
            # días u horas (de la lista que mandó la agenda); cualquier otro id
            # "cita_" (p. ej. un [Confirmar] tocado dos veces) se ignora.
            if id_interactivo and id_interactivo.startswith((PREFIJO_FILA_DIA, PREFIJO_FILA_HORA, PREFIJO_FILA_MAS_DIAS)):
                cita_id = self._citas.crear_en_construccion(numero, self._perfil, ahora)
                logger.info("Solicitud de cita #%s iniciada (remitente=%s)", cita_id, enmascarar_numero(numero))
                cita = self._citas.obtener(cita_id)
            else:
                logger.info("Interacción de cita sin cita en construcción, ignorada (remitente=%s)", enmascarar_numero(numero))
                return
        elif ahora - cita["actualizado_en"] > SEGUNDOS_TIMEOUT_CITA:
            self._citas.cancelar(cita["id"], ahora)
            logger.info("Solicitud de cita #%s cancelada por inactividad (remitente=%s)", cita["id"], enmascarar_numero(numero))
            self._enviar_texto(numero, MENSAJE_CANCELADA_POR_INACTIVIDAD)
            return

        texto = mensaje.get("text", {}).get("body") if mensaje.get("type") == "text" else None
        normalizado = _normalizar(texto) if texto is not None else None

        if normalizado in PALABRAS_CLAVE_CANCELAR or id_interactivo == ID_BOTON_CANCELAR:
            self._cancelar(numero, cita, ahora)
            return
        if normalizado in PALABRAS_CLAVE_PERSONA:
            self._citas.cancelar(cita["id"], ahora)
            logger.info("Solicitud de cita #%s cancelada y derivada a una persona (remitente=%s)",
                        cita["id"], enmascarar_numero(numero))
            self._enviar_texto(numero, self._mensaje_derivacion)
            self._avisar_derivacion(numero, "El cliente pidió hablar con un asesor mientras agendaba una cita.", ahora)
            return

        # Filas de día/hora y paginación se aceptan en los pasos de elegir
        # horario (también desde una lista anterior); en los demás pasos se
        # tratan como entrada no reconocida.
        if cita["paso"] in (PASO_DIA, PASO_HORA) and id_interactivo:
            if self._manejar_fila_de_horario(numero, cita, id_interactivo, ahora):
                return

        if cita["paso"] == PASO_CONSENTIMIENTO:
            if id_interactivo == ID_BOTON_ACEPTO:
                self._citas.registrar_consentimiento(cita["id"], PASO_CONSENTIMIENTO, ahora)
                self._avanzar(numero, self._citas.obtener(cita["id"]), ahora)
                return
            if id_interactivo == ID_BOTON_NO_ACEPTO:
                self._no_acepta(numero, cita, ahora)
                return

        if cita["paso"].startswith(PREFIJO_PASO_DATO):
            self._manejar_dato(numero, cita, texto, ahora)
            return

        if cita["paso"] == PASO_CONFIRMACION:
            if id_interactivo == ID_BOTON_CONFIRMAR:
                self._confirmar(numero, cita, ahora)
                return
            if id_interactivo == ID_BOTON_CAMBIAR:
                self._citas.fijar_paso(cita["id"], PASO_DIA, ahora)
                self.ofrecer_dias(numero)
                return

        logger.info("Entrada no reconocida en la cita #%s (paso=%s, remitente=%s)",
                    cita["id"], cita["paso"], enmascarar_numero(numero))
        self._citas.fijar_paso(cita["id"], cita["paso"], ahora)  # renueva la inactividad
        self._enviar_texto(numero, MENSAJE_ENTRADA_NO_RECONOCIDA)
        self._reenviar_paso(numero, cita)

    # -- Pasos --

    def _manejar_fila_de_horario(self, numero: str, cita: dict, id_fila: str, ahora: float) -> bool:
        if id_fila.startswith(PREFIJO_FILA_MAS_DIAS):
            pagina = id_fila[len(PREFIJO_FILA_MAS_DIAS):]
            if pagina.isdigit() and int(pagina) >= 1:
                self._citas.fijar_paso(cita["id"], PASO_DIA, ahora)
                self.ofrecer_dias(numero, numero_pagina=int(pagina))
                return True
            return False

        if id_fila == ID_FILA_OTRO_DIA:
            self._citas.fijar_paso(cita["id"], PASO_DIA, ahora)
            self.ofrecer_dias(numero)
            return True

        if id_fila.startswith(PREFIJO_FILA_MAS_HORAS):
            fecha_texto, _, pagina = id_fila[len(PREFIJO_FILA_MAS_HORAS):].rpartition("_")
            fecha = _fecha_o_none(fecha_texto)
            if fecha is None or not pagina.isdigit() or int(pagina) < 1:
                return False
            if not self._ofrecer_horas(numero, fecha, numero_pagina=int(pagina)):
                self._enviar_texto(numero, MENSAJE_DIA_NO_DISPONIBLE)
                self.ofrecer_dias(numero)
            return True

        if id_fila.startswith(PREFIJO_FILA_DIA):
            fecha = _fecha_o_none(id_fila[len(PREFIJO_FILA_DIA):])
            if fecha is None:
                return False
            self._citas.fijar_fecha(cita["id"], fecha.isoformat(), PASO_HORA, ahora)
            if not self._ofrecer_horas(numero, fecha):
                self._citas.fijar_paso(cita["id"], PASO_DIA, ahora)
                self.ofrecer_dias(numero, cuerpo=MENSAJE_DIA_NO_DISPONIBLE)
            return True

        if id_fila.startswith(PREFIJO_FILA_HORA):
            inicio = id_fila[len(PREFIJO_FILA_HORA):].replace("_", " ", 1)
            if not agenda.inicio_disponible(self._config, inicio, ahora, self._ocupacion(ahora)):
                logger.info("Horario no disponible elegido en la cita #%s (remitente=%s)", cita["id"], enmascarar_numero(numero))
                self._reofrecer_tras_horario_perdido(numero, cita, inicio, MENSAJE_HORARIO_NO_DISPONIBLE, ahora)
                return True
            self._citas.fijar_fecha(cita["id"], inicio[:10], PASO_HORA, ahora)
            self._citas.fijar_inicio(cita["id"], inicio, PASO_HORA, ahora)
            self._avanzar(numero, self._citas.obtener(cita["id"]), ahora)
            return True

        return False

    def _reofrecer_tras_horario_perdido(self, numero: str, cita: dict, inicio: str, mensaje: str, ahora: float) -> None:
        fecha = _fecha_o_none(inicio[:10]) if isinstance(inicio, str) else None
        if fecha is not None:
            self._citas.fijar_fecha(cita["id"], fecha.isoformat(), PASO_HORA, ahora)
            if self._ofrecer_horas(numero, fecha, cuerpo=mensaje):
                return
        self._citas.fijar_paso(cita["id"], PASO_DIA, ahora)
        self.ofrecer_dias(numero, cuerpo=MENSAJE_DIA_NO_DISPONIBLE)

    def _siguiente_paso(self, cita: dict) -> str:
        if cita["inicio"] is None:
            return PASO_DIA
        if cita["consentimiento_en"] is None:
            return PASO_CONSENTIMIENTO
        for dato in self._config["datos"]:
            if dato["clave"] not in cita["datos"]:
                return f'{PREFIJO_PASO_DATO}{dato["clave"]}'
        return PASO_CONFIRMACION

    def _avanzar(self, numero: str, cita: dict, ahora: float) -> None:
        paso = self._siguiente_paso(cita)
        self._citas.fijar_paso(cita["id"], paso, ahora)
        cita = {**cita, "paso": paso}
        self._reenviar_paso(numero, cita)

    def _pregunta_de(self, paso: str) -> str:
        clave = paso[len(PREFIJO_PASO_DATO):]
        return next(d["pregunta"] for d in self._config["datos"] if d["clave"] == clave)

    def _reenviar_paso(self, numero: str, cita: dict) -> None:
        paso = cita["paso"]
        if paso == PASO_DIA:
            self.ofrecer_dias(numero)
        elif paso == PASO_HORA:
            fecha = _fecha_o_none(cita["fecha"] or "")
            if fecha is None or not self._ofrecer_horas(numero, fecha):
                self.ofrecer_dias(numero)
        elif paso == PASO_CONSENTIMIENTO:
            self._enviar_botones(numero, TEXTO_CONSENTIMIENTO, [(ID_BOTON_ACEPTO, "Acepto"), (ID_BOTON_NO_ACEPTO, "No acepto")])
        elif paso.startswith(PREFIJO_PASO_DATO):
            self._enviar_texto(numero, self._pregunta_de(paso))
        elif paso == PASO_CONFIRMACION:
            resumen = (
                f'Resumen de su cita:\nFecha y hora: {fecha_hora_legible(cita["inicio"])}\n'
                f'{datos_multilinea(self._config, cita["datos"])}\n¿Confirmamos la cita?'
            )
            self._enviar_botones(
                numero, resumen,
                [(ID_BOTON_CONFIRMAR, "Confirmar"), (ID_BOTON_CAMBIAR, "Cambiar horario"), (ID_BOTON_CANCELAR, "Cancelar")],
            )

    def _manejar_dato(self, numero: str, cita: dict, texto: str | None, ahora: float) -> None:
        pregunta = self._pregunta_de(cita["paso"])
        valor = una_linea(texto or "", LIMITE_DATO)
        if not valor:
            self._citas.fijar_paso(cita["id"], cita["paso"], ahora)
            self._enviar_texto(numero, MENSAJE_DATO_INVALIDO.format(pregunta=pregunta))
            return
        clave = cita["paso"][len(PREFIJO_PASO_DATO):]
        self._citas.guardar_dato(cita["id"], clave, valor, cita["paso"], ahora)
        self._avanzar(numero, self._citas.obtener(cita["id"]), ahora)

    def _no_acepta(self, numero: str, cita: dict, ahora: float) -> None:
        self._citas.cancelar(cita["id"], ahora)
        logger.info("Solicitud de cita #%s: no aceptó el tratamiento de datos (remitente=%s)",
                    cita["id"], enmascarar_numero(numero))
        mensaje = MENSAJE_NO_ACEPTA
        if self._config.get("telefono_negocio"):
            mensaje += MENSAJE_NO_ACEPTA_TELEFONO.format(telefono=self._config["telefono_negocio"])
        self._enviar_texto(numero, f"{mensaje} {self._mensaje_derivacion}")
        self._avisar_derivacion(
            numero, "El cliente quería agendar una cita pero no autorizó el tratamiento de datos por este medio.", ahora
        )

    def _cancelar(self, numero: str, cita: dict, ahora: float) -> None:
        self._citas.cancelar(cita["id"], ahora)
        logger.info("Solicitud de cita #%s cancelada por el cliente (remitente=%s)", cita["id"], enmascarar_numero(numero))
        self._enviar_texto(numero, MENSAJE_CITA_CANCELADA)

    def _confirmar(self, numero: str, cita: dict, ahora: float) -> None:
        # Pasado, anticipación o día que dejó de atenderse: se revisa con el
        # reloj actual (el cliente pudo tardar en confirmar). El cupo y el tope
        # se garantizan en la sentencia atómica de Citas.confirmar.
        if not agenda.inicio_disponible(self._config, cita["inicio"], ahora, {}):
            self._reofrecer_tras_horario_perdido(numero, cita, cita["inicio"], MENSAJE_HORARIO_NO_DISPONIBLE, ahora)
            return

        desde = agenda.texto_inicio(agenda.ahora_bogota(ahora))
        resultado = self._citas.confirmar(
            cita["id"], self._config["cupos_por_horario"], self._config["max_citas_por_cliente"], desde, ahora
        )
        if resultado == RESULTADO_CONFIRMADA:
            cita = self._citas.obtener(cita["id"])
            logger.info("Cita #%s confirmada (remitente=%s)", cita["id"], enmascarar_numero(numero))
            self._enviar_texto(numero, MENSAJE_CITA_CONFIRMADA.format(
                id=cita["id"], fecha_hora=fecha_hora_legible(cita["inicio"]),
                datos=datos_multilinea(self._config, cita["datos"]),
            ))
            self._avisar_cita_nueva(cita, ahora)
        elif resultado == RESULTADO_CUPO_LLENO:
            logger.info("Cupo ocupado al confirmar la cita #%s (remitente=%s)", cita["id"], enmascarar_numero(numero))
            self._reofrecer_tras_horario_perdido(numero, cita, cita["inicio"], MENSAJE_HORARIO_OCUPADO_AL_CONFIRMAR, ahora)
        elif resultado == RESULTADO_TOPE_CLIENTE:
            self._citas.cancelar(cita["id"], ahora)
            logger.info("Tope de citas por cliente alcanzado en la cita #%s (remitente=%s)",
                        cita["id"], enmascarar_numero(numero))
            self._enviar_texto(numero, MENSAJE_TOPE.format(maximo=self._config["max_citas_por_cliente"]))
        # RESULTADO_NO_EN_CONSTRUCCION / SIN_HORARIO: doble toque o estado
        # inesperado; no se envía nada más.

    # -- Avisos al dueño --

    def _avisar_derivacion(self, numero: str, resumen: str, ahora: float) -> None:
        derivacion.avisar_derivacion(
            self._pedidos, self._numero_dueno, numero, resumen, ahora, self._enviar_texto_con_wamid_fn,
            enviar_plantilla_fn=self._enviar_plantilla_fn,
            plantilla_nombre=self._plantilla_aviso_derivacion_nombre,
            plantilla_idioma=self._plantilla_aviso_derivacion_idioma,
        )

    def _avisar_cita_nueva(self, cita: dict, ahora: float) -> None:
        """Teléfono completo del cliente en el contenido (misma excepción
        deliberada del aviso de pedido nuevo); enmascarado en el log."""
        if not self._numero_dueno or cita["estado"] != ESTADO_CONFIRMADA:
            return
        fecha_hora = fecha_hora_legible(cita["inicio"])
        datos = datos_una_linea(self._config, cita["datos"])
        if self._plantilla_aviso_cita_nombre and self._plantilla_aviso_cita_idioma and self._enviar_plantilla_fn:
            canal = "plantilla"
            ok, wamid = self._enviar_plantilla_fn(
                self._numero_dueno, self._plantilla_aviso_cita_nombre, self._plantilla_aviso_cita_idioma,
                [str(cita["id"]), fecha_hora, datos, cita["numero_cliente"]],
            )
        else:
            canal = "texto libre"
            ok, wamid = self._enviar_texto_con_wamid_fn(
                self._numero_dueno,
                f'Nueva cita #{cita["id"]} agendada.\nFecha y hora: {fecha_hora}\n'
                f'{datos_multilinea(self._config, cita["datos"])}\nTeléfono del cliente: {cita["numero_cliente"]}',
            )
        if ok and wamid:
            self._citas.fijar_wamid_aviso(cita["id"], wamid)
        if ok:
            logger.info("Cita #%s: aviso de cita nueva enviado al dueño por %s (cliente=%s)",
                        cita["id"], canal, enmascarar_numero(cita["numero_cliente"]))
        else:
            logger.warning("No se pudo enviar el aviso de la cita #%s al dueño (%s).", cita["id"], canal)


# -- Vista del dueño: palabra "citas" (mismo patrón que "pedidos") --

PALABRAS_CLAVE_CITAS = {"citas"}
PREFIJO_FILA_VER_CITA = "ver_cita_"
PREFIJO_FILA_PAGINA_CITAS = "citas_pagina_"
CITAS_POR_PAGINA_CON_VER_MAS = MAXIMO_FILAS_LISTA - 1
LISTA_CITAS_CUERPO = "Próximas citas agendadas, de la más cercana a la más lejana. Toque una para ver el detalle."
LISTA_CITAS_BOTON = "Ver citas"
LISTA_CITAS_SECCION = "Próximas citas"
MENSAJE_SIN_CITAS = "No hay citas próximas agendadas."
MENSAJE_AGENDA_NO_ACTIVA = "Este negocio no tiene la agenda de citas activada."


def interpretar_fila_dueno(id_fila: str) -> tuple[str, int] | None:
    """("ver", id_cita) o ("pagina", numero) para las filas de la lista de citas del dueño."""
    for prefijo, tipo in ((PREFIJO_FILA_VER_CITA, "ver"), (PREFIJO_FILA_PAGINA_CITAS, "pagina")):
        if id_fila.startswith(prefijo):
            valor = id_fila[len(prefijo):]
            if valor.isdigit() and int(valor) >= 1:
                return tipo, int(valor)
    return None


def pagina_de_proximas_citas(citas: Citas, perfil: str, config: dict, ahora: float, numero_pagina: int = 1) -> list[dict] | None:
    """Secciones para enviar_lista (sin teléfono), o None si no hay citas en esa página."""
    desde = agenda.texto_inicio(agenda.ahora_bogota(ahora))
    desplazamiento = (numero_pagina - 1) * CITAS_POR_PAGINA_CON_VER_MAS
    restantes = citas.listar_proximas(perfil, desde, desplazamiento, MAXIMO_FILAS_LISTA + 1)
    if not restantes:
        return None
    hay_mas = len(restantes) > MAXIMO_FILAS_LISTA
    visibles = restantes[:CITAS_POR_PAGINA_CON_VER_MAS] if hay_mas else restantes
    primer_dato = config["datos"][0]
    filas = []
    for cita in visibles:
        fecha = agenda.momento_desde_inicio(cita["inicio"]).date()
        valor = cita["datos"].get(primer_dato["clave"], "")
        filas.append({
            "id": f'{PREFIJO_FILA_VER_CITA}{cita["id"]}',
            "titulo": una_linea(f'{dia_corto(fecha)} {hora_legible(cita["inicio"])}', 24),
            "descripcion": una_linea(f'#{cita["id"]} · {primer_dato["etiqueta"]}: {valor}' if valor else f'#{cita["id"]}', 72),
        })
    if hay_mas:
        filas.append({"id": f"{PREFIJO_FILA_PAGINA_CITAS}{numero_pagina + 1}", "titulo": "Ver más", "descripcion": "Siguientes citas"})
    return [{"titulo": LISTA_CITAS_SECCION, "filas": filas}]


def detalle_cita_para_dueno(cita: dict | None, config: dict) -> str:
    if cita is None or cita["estado"] != ESTADO_CONFIRMADA:
        return "Esa cita ya no está agendada."
    return (
        f'Cita #{cita["id"]}\nFecha y hora: {fecha_hora_legible(cita["inicio"])}\n'
        f'{datos_multilinea(config, cita["datos"])}\nTeléfono del cliente: {cita["numero_cliente"]}'
    )


def aplicar_retencion(citas: Citas, perfil: str, config: dict, ahora: float) -> int:
    """Anonimiza los datos personales de las citas vencidas según
    `retencion_dias` (Ley 1581). Se programa a diario desde gunicorn."""
    dias = config["retencion_dias"]
    limite_inicio = agenda.texto_inicio(agenda.ahora_bogota(ahora - dias * 86400))
    borradas = citas.borrar_datos_vencidos(perfil, limite_inicio, ahora - dias * 86400)
    logger.info("Retención de citas: %d cita(s) anonimizada(s) (más de %d días).", borradas, dias)
    return borradas


def iniciar_programador_retencion(tarea):
    """Ejecuta `tarea` ya y luego cada día a las 3:00 a.m. de Bogotá. Se arranca
    desde gunicorn.conf.py (post_worker_init), igual que el reporte semanal,
    para que las pruebas nunca lancen hilos. La tarea es idempotente."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    programador = BackgroundScheduler(timezone=agenda.ZONA_BOGOTA)
    programador.add_job(
        tarea, CronTrigger(hour=3, minute=0, timezone=agenda.ZONA_BOGOTA),
        id="retencion_citas", max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    programador.add_job(tarea, id="retencion_citas_al_arrancar")
    programador.start()
    return programador


def _fecha_o_none(texto: str) -> date | None:
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None
