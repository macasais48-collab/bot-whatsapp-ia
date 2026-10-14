import requests
from dotenv import load_dotenv

from env import obtener_env


def main() -> None:
    load_dotenv()

    token = obtener_env("WHATSAPP_TOKEN")
    version = obtener_env("GRAPH_API_VERSION")
    waba_id = obtener_env("WHATSAPP_WABA_ID")

    if not token or not version or not waba_id:
        print("Falta WHATSAPP_TOKEN, GRAPH_API_VERSION o WHATSAPP_WABA_ID en el entorno.")
        return

    url = f"https://graph.facebook.com/{version}/{waba_id}/subscribed_apps"

    try:
        respuesta = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    except requests.exceptions.RequestException as error:
        print(f"Fallo de red al consultar subscribed_apps (tipo={type(error).__name__}).")
        return

    if respuesta.status_code != 200:
        detalle = {}
        try:
            detalle = respuesta.json().get("error", {})
        except ValueError:
            pass
        print(
            f"GET falló. status={respuesta.status_code}, "
            f"error.code={detalle.get('code')}, "
            f"error.error_subcode={detalle.get('error_subcode')}, "
            f"error.message={detalle.get('message')}"
        )
        return

    datos = respuesta.json().get("data", [])

    if not datos:
        print("La lista de apps suscritas está VACÍA. La WABA no tiene ninguna app suscrita.")
        return

    print(f"Hay {len(datos)} app(s) suscrita(s) a esta WABA:")
    for entrada in datos:
        info = entrada.get("whatsapp_business_api_data", {})
        print(f"- id de app: {info.get('id')}, nombre: {info.get('name')}")


if __name__ == "__main__":
    main()
