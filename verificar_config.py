from dotenv import dotenv_values

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
]


def generar_reporte(valores: dict) -> str:
    lineas = []
    for nombre in VARIABLES_ESPERADAS:
        valor = (valores.get(nombre) or "").strip()
        estado = "con valor" if valor else "VACÍO"
        lineas.append(f"{nombre}: {estado}")
    return "\n".join(lineas)


def main(ruta_env: str = ".env") -> None:
    valores = dotenv_values(ruta_env)
    print(generar_reporte(valores))


if __name__ == "__main__":
    main()
