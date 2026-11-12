from dotenv import dotenv_values

from telefono import normalizar_numero, numero_parece_valido

VARIABLES_ESPERADAS = [
    "PROVEEDOR_IA",
    "ANTHROPIC_API_KEY",
    "MODELO_IA",
    "MAX_TURNOS_HISTORIAL",
    "WHATSAPP_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "META_APP_SECRET",
    "GRAPH_API_VERSION",
    "WHATSAPP_WABA_ID",
    "PUERTO",
    "PERFIL_NEGOCIO",
    "NUMERO_DUENO",
    "PLANTILLA_AVISO_DUENO_NOMBRE",
    "PLANTILLA_AVISO_DUENO_IDIOMA",
    "PLANTILLA_AVISO_PEDIDO_NUEVO_NOMBRE",
    "PLANTILLA_AVISO_PEDIDO_NUEVO_IDIOMA",
    "REPORTE_SEMANAL_DIA",
    "REPORTE_SEMANAL_HORA",
    "PLANTILLA_REPORTE_SEMANAL_NOMBRE",
    "PLANTILLA_REPORTE_SEMANAL_IDIOMA",
]

# Vacías es un estado válido: el bot usa su comportamiento por defecto (lunes
# 8:00 para el reporte; mensaje libre si no hay plantilla).
VARIABLES_OPCIONALES = {
    "REPORTE_SEMANAL_DIA",
    "REPORTE_SEMANAL_HORA",
    "PLANTILLA_REPORTE_SEMANAL_NOMBRE",
    "PLANTILLA_REPORTE_SEMANAL_IDIOMA",
}


def generar_reporte(valores: dict) -> str:
    lineas = []
    for nombre in VARIABLES_ESPERADAS:
        valor = (valores.get(nombre) or "").strip()
        if not valor:
            sufijo = " (opcional)" if nombre in VARIABLES_OPCIONALES else ""
            lineas.append(f"{nombre}: VACÍO{sufijo}")
            continue
        estado = "con valor"
        if nombre == "NUMERO_DUENO" and not numero_parece_valido(normalizar_numero(valor)):
            estado += " (formato no parece válido; revise que sea solo el número con código de " \
                "país, sin '+', espacios ni guiones)"
        lineas.append(f"{nombre}: {estado}")
    return "\n".join(lineas)


def main(ruta_env: str = ".env") -> None:
    valores = dotenv_values(ruta_env)
    print(generar_reporte(valores))


if __name__ == "__main__":
    main()
