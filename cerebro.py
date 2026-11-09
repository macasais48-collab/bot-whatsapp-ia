import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays

from env import obtener_env
from historial import Historial
from llm.base import ProveedorIA
from recursos import cargar_recursos

logger = logging.getLogger(__name__)

RUTA_NEGOCIO_POR_DEFECTO = Path(__file__).parent / "negocio.md"

ZONA_BOGOTA = ZoneInfo("America/Bogota")

DIAS_SEMANA_ES = {
    0: "lunes",
    1: "martes",
    2: "miércoles",
    3: "jueves",
    4: "viernes",
    5: "sábado",
    6: "domingo",
}

DIAS_FESTIVOS_A_FUTURO = 90

MENSAJE_SEGURO = (
    "No tengo esa información disponible en este momento. "
    "Te voy a derivar con una persona para que te ayude mejor."
)


def _reloj_por_defecto() -> datetime:
    return datetime.now(ZONA_BOGOTA)


@dataclass
class Respuesta:
    texto: str
    derivar: bool
    adjuntos: list = field(default_factory=list)


class Cerebro:
    def __init__(
        self,
        proveedor_ia: ProveedorIA,
        historial: Historial,
        ruta_negocio: Path = RUTA_NEGOCIO_POR_DEFECTO,
        ruta_recursos: Path | None = None,
        reloj=_reloj_por_defecto,
    ) -> None:
        self._proveedor_ia = proveedor_ia
        self._historial = historial
        self._reloj = reloj
        self._festivos_colombia = holidays.Colombia()
        try:
            self._max_turnos = int(obtener_env("MAX_TURNOS_HISTORIAL", "6"))
        except ValueError:
            # No se re-lanza la excepción original: su mensaje incluye el valor
            # inválido de la variable de entorno.
            raise ValueError("MAX_TURNOS_HISTORIAL no es válido. Debe ser un número entero.") from None
        # Falla al arrancar si el JSON de recursos del perfil está mal formado,
        # igual que con PERFIL_NEGOCIO: mejor un error claro ahora que uno confuso
        # a mitad de una conversación real.
        self._recursos = cargar_recursos(ruta_recursos) if ruta_recursos is not None else {}
        self._prompt_base = (
            self._construir_prompt_base(ruta_negocio) + "\n\n" + self._construir_descripcion_recursos()
        )

    def _construir_contexto_fecha(self) -> str:
        ahora = self._reloj()
        hoy = ahora.date()
        mañana = hoy + timedelta(days=1)

        dia_semana_hoy = DIAS_SEMANA_ES[hoy.weekday()]
        dia_semana_manana = DIAS_SEMANA_ES[mañana.weekday()]
        hoy_festivo = hoy in self._festivos_colombia
        manana_festivo = mañana in self._festivos_colombia

        proximos_festivos = []
        for i in range(DIAS_FESTIVOS_A_FUTURO + 1):
            dia = hoy + timedelta(days=i)
            nombre = self._festivos_colombia.get(dia)
            if nombre:
                # La librería agrega "(observado)" cuando el festivo se traslada a otro
                # día (Ley Emiliani); se quita porque no aporta nada a un cliente del bot.
                nombre = nombre.replace(" (observado)", "")
                proximos_festivos.append(f"{dia.isoformat()} {DIAS_SEMANA_ES[dia.weekday()]} ({nombre})")
        lista_festivos = ", ".join(proximos_festivos) if proximos_festivos else "ninguno"

        return (
            "Contexto de fecha y hora (zona horaria America/Bogota):\n"
            f"- Hoy es {dia_semana_hoy}, {hoy.isoformat()}, hora {ahora.strftime('%H:%M')}. "
            f"{'Hoy es festivo en Colombia.' if hoy_festivo else 'Hoy no es festivo en Colombia.'}\n"
            f"- Mañana es {dia_semana_manana}, {mañana.isoformat()}. "
            f"{'Mañana es festivo en Colombia.' if manana_festivo else 'Mañana no es festivo en Colombia.'}\n"
            f"- Festivos en Colombia en los próximos {DIAS_FESTIVOS_A_FUTURO} días: {lista_festivos}. "
            "En cualquiera de esas fechas (o en cualquier otro festivo colombiano que el "
            "cliente mencione), aplica el horario de festivos del negocio: si el negocio "
            "cierra los festivos, responde que ese día está cerrado."
        )

    def _construir_prompt_base(self, ruta_negocio: Path) -> str:
        info_negocio = ruta_negocio.read_text(encoding="utf-8")
        return (
            "Eres el asistente de atención al cliente de este negocio. "
            "Responde SIEMPRE en español, de forma breve y amable, "
            "usando ÚNICAMENTE la información del negocio que se incluye a continuación. "
            "Nunca inventes datos que no estén en esa información. "
            "Si la respuesta a la pregunta del cliente no está en esa información, "
            "dilo con honestidad y marca que se debe derivar a una persona.\n\n"
            "Responde SIEMPRE y SOLO con un objeto JSON válido, sin texto adicional "
            "antes ni después, con exactamente esta forma:\n"
            '{"respuesta": "<tu respuesta en español>", "derivar": true o false, '
            '"adjuntos": [<opcional: objetos como {"tipo": "ubicacion"}, '
            '{"tipo": "enlace", "clave": "<clave>"}, {"tipo": "imagen", "clave": "<clave>"}, '
            '{"tipo": "botones", "clave": "<clave>"} o {"tipo": "menu"}>]}\n\n'
            "El campo 'adjuntos' es opcional: inclúyelo solo con las claves listadas en "
            "'Recursos disponibles' más abajo, cuando le sirvan al cliente. Nunca inventes "
            "una clave, URL o coordenada que no esté en esa lista. Si no hace falta ningún "
            "adjunto, omite el campo o deja la lista vacía. Si incluyes un adjunto, el texto "
            "de 'respuesta' debe anunciarlo como algo que ya se está enviando (por ejemplo "
            "'Le comparto una foto...' o 'Le comparto la ubicación...'), nunca preguntar si "
            "lo quiere ver — eso sería contradictorio, porque el adjunto se envía de todas "
            "formas en el mismo momento.\n\n"
            "Información del negocio:\n"
            f"{info_negocio}"
        )

    def _construir_descripcion_recursos(self) -> str:
        if not self._recursos:
            return "Recursos disponibles para adjuntar: ninguno en este perfil."

        lineas = ["Recursos disponibles para adjuntar (usa SOLO estas claves cuando ayuden al cliente):"]
        enlaces = self._recursos.get("enlaces", {})
        tiene_ubicacion = "ubicacion" in self._recursos
        # Convención del proyecto: cuando un perfil tiene botón de mapa, su clave es
        # "mapa". Si además tiene "ubicacion", antes se describían como dos recursos
        # independientes y la IA a veces solo adjuntaba uno de los dos al preguntarle
        # por la dirección (ambigüedad real observada en vivo con el perfil "tamales").
        tiene_mapa = "mapa" in enlaces

        if tiene_ubicacion and tiene_mapa:
            lineas.append(
                '- {"tipo": "ubicacion"} y {"tipo": "enlace", "clave": "mapa"}: comparten juntos '
                "la ubicación del negocio y el botón para ver el mapa. Cuando el cliente pregunte "
                "dónde queda, pida la dirección o un mapa, incluye SIEMPRE los dos adjuntos juntos, "
                "nunca uno solo."
            )
        elif tiene_ubicacion:
            lineas.append(
                '- {"tipo": "ubicacion"}: comparte la ubicación del negocio. Úsalo cuando '
                "el cliente pregunte dónde queda, pida la dirección o un mapa."
            )

        for clave, enlace in enlaces.items():
            if tiene_ubicacion and tiene_mapa and clave == "mapa":
                continue
            lineas.append(
                f'- {{"tipo": "enlace", "clave": "{clave}"}}: botón "{enlace["texto_boton"]}".'
            )
        for clave, imagen in self._recursos.get("imagenes", {}).items():
            lineas.append(
                f'- {{"tipo": "imagen", "clave": "{clave}"}}: {imagen["descripcion"]}'
            )
        for clave, conjunto in self._recursos.get("botones", {}).items():
            titulos = ", ".join(f'"{opcion["titulo"]}"' for opcion in conjunto["opciones"])
            lineas.append(
                f'- {{"tipo": "botones", "clave": "{clave}"}}: botones de respuesta rápida ({titulos}).'
            )
        if self._recursos.get("catalogo"):
            lineas.append(
                '- {"tipo": "menu"}: muestra el menú completo del negocio como una lista, armada '
                "automáticamente con los nombres y precios reales del catálogo (nunca inventes "
                "productos ni precios: esta lista los toma directo del catálogo). Úsalo cuando el "
                "cliente pregunte qué venden o pida ver el menú."
            )
        return "\n".join(lineas)

    def _resolver_adjunto(self, item: dict) -> dict | None:
        tipo = item.get("tipo")
        if tipo == "ubicacion":
            datos_ubicacion = self._recursos.get("ubicacion")
            if datos_ubicacion is not None:
                return {"tipo": "ubicacion", "datos": datos_ubicacion}
            return None
        if tipo == "enlace":
            enlace = self._recursos.get("enlaces", {}).get(item.get("clave"))
            if enlace is not None:
                return {"tipo": "enlace", "datos": enlace}
            return None
        if tipo == "imagen":
            imagen = self._recursos.get("imagenes", {}).get(item.get("clave"))
            if imagen is not None:
                return {"tipo": "imagen", "datos": imagen}
            return None
        if tipo == "botones":
            conjunto = self._recursos.get("botones", {}).get(item.get("clave"))
            if conjunto is not None:
                return {"tipo": "botones", "datos": conjunto}
            return None
        if tipo == "menu":
            catalogo = self._recursos.get("catalogo")
            if catalogo:
                return {"tipo": "menu", "datos": catalogo}
            return None
        return None

    def _resolver_adjuntos(self, bruto) -> list:
        # Nunca debe propagar una excepción: un adjunto mal formado jamás puede
        # tirar abajo la respuesta de texto que ya se validó.
        try:
            if not isinstance(bruto, list):
                if bruto:
                    logger.warning("Campo 'adjuntos' con forma inesperada, se ignora: %r", bruto)
                return []

            resultado = []
            for item in bruto:
                if not isinstance(item, dict):
                    logger.warning("Adjunto descartado: no es un objeto (%r).", item)
                    continue
                adjunto_resuelto = self._resolver_adjunto(item)
                if adjunto_resuelto is None:
                    logger.warning("Adjunto descartado (tipo o clave inexistente en el perfil): %r", item)
                else:
                    resultado.append(adjunto_resuelto)
            return resultado
        except Exception:
            logger.warning("Error inesperado al procesar 'adjuntos'; se omiten todos.", exc_info=True)
            return []

    def _registrar_fallo_ia(self, error: Exception) -> None:
        # Nunca incluye el texto del cliente, el prompt ni ningún dato personal:
        # solo el tipo de fallo, para poder diagnosticar en producción límites de
        # tasa (429), timeouts o errores del servidor de la IA. No se importa un
        # SDK concreto (ProveedorIA es una interfaz común a Claude y OpenAI): se
        # usa el atributo 'status_code' que ambos SDK exponen en sus excepciones.
        codigo = getattr(error, "status_code", None)
        tipo = type(error).__name__
        if codigo == 429:
            categoria = "limite_de_tasa_429"
        elif "timeout" in tipo.lower():
            categoria = "timeout"
        elif isinstance(codigo, int) and codigo >= 500:
            categoria = "error_del_servidor"
        elif codigo is not None:
            categoria = f"error_http_{codigo}"
        else:
            categoria = "desconocido"
        logger.warning(
            "Fallo al llamar a la IA (categoria=%s, tipo_excepcion=%s)", categoria, tipo
        )

    def responder(self, id_conversacion: str, texto: str) -> Respuesta:
        mensajes_previos = self._historial.obtener(id_conversacion, self._max_turnos)
        mensajes = mensajes_previos + [{"role": "user", "content": texto}]

        respuesta_texto = MENSAJE_SEGURO
        derivar = True
        adjuntos_validos = []

        try:
            prompt_completo = self._prompt_base + "\n\n" + self._construir_contexto_fecha()
            try:
                salida = self._proveedor_ia.responder(prompt_completo, mensajes)
            except Exception as error:
                self._registrar_fallo_ia(error)
                raise
            datos = json.loads(salida)
            candidato_texto = datos["respuesta"]
            candidato_derivar = datos["derivar"]
            if isinstance(candidato_texto, str) and isinstance(candidato_derivar, bool):
                respuesta_texto = candidato_texto
                derivar = candidato_derivar
                # _resolver_adjuntos nunca lanza: un adjunto inválido no puede
                # invalidar la respuesta de texto que ya se validó arriba.
                adjuntos_validos = self._resolver_adjuntos(datos.get("adjuntos", []))
        except Exception:
            # Límite del sistema: JSON inválido, claves faltantes o fallo de la API
            # externa. En cualquiera de esos casos se usa el mensaje seguro.
            pass

        self._historial.agregar(id_conversacion, "user", texto)
        self._historial.agregar(id_conversacion, "assistant", respuesta_texto)

        return Respuesta(texto=respuesta_texto, derivar=derivar, adjuntos=adjuntos_validos)
