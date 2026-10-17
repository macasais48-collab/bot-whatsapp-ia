import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays

from env import obtener_env
from historial import Historial
from llm.base import ProveedorIA

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


class Cerebro:
    def __init__(
        self,
        proveedor_ia: ProveedorIA,
        historial: Historial,
        ruta_negocio: Path = RUTA_NEGOCIO_POR_DEFECTO,
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
        self._prompt_base = self._construir_prompt_base(ruta_negocio)

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
            '{"respuesta": "<tu respuesta en español>", "derivar": true o false}\n\n'
            "Información del negocio:\n"
            f"{info_negocio}"
        )

    def responder(self, id_conversacion: str, texto: str) -> Respuesta:
        mensajes_previos = self._historial.obtener(id_conversacion, self._max_turnos)
        mensajes = mensajes_previos + [{"role": "user", "content": texto}]

        respuesta_texto = MENSAJE_SEGURO
        derivar = True

        try:
            prompt_completo = self._prompt_base + "\n\n" + self._construir_contexto_fecha()
            salida = self._proveedor_ia.responder(prompt_completo, mensajes)
            datos = json.loads(salida)
            candidato_texto = datos["respuesta"]
            candidato_derivar = datos["derivar"]
            if isinstance(candidato_texto, str) and isinstance(candidato_derivar, bool):
                respuesta_texto = candidato_texto
                derivar = candidato_derivar
        except Exception:
            # Límite del sistema: JSON inválido, claves faltantes o fallo de la API
            # externa. En cualquiera de esos casos se usa el mensaje seguro.
            pass

        self._historial.agregar(id_conversacion, "user", texto)
        self._historial.agregar(id_conversacion, "assistant", respuesta_texto)

        return Respuesta(texto=respuesta_texto, derivar=derivar)
