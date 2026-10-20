# BotWhatsApp

Asistente de WhatsApp con IA para pequeños negocios, demostrado aquí con un negocio ficticio: la **Panadería San Roque**.

## Demostración

### 1. Horario con fecha real

Responde con el horario real y calcula correctamente qué día es "mañana" (contexto de fecha, no una fecha inventada).

<img src="docs/capturas/01-horario.png" alt="Horario" width="700">

### 2. No inventa productos

No inventa un producto que no existe en el menú; ofrece alternativas reales en su lugar.

<img src="docs/capturas/02-productos.png" alt="Productos" width="700">

### 3. Domicilios

Responde sobre zonas de domicilio, costo y pedido mínimo con datos exactos del negocio.

<img src="docs/capturas/03-domicilio.png" alt="Domicilios" width="700">

### 4. Derivación a una persona

Ante una pregunta fuera de lo que sabe, lo admite y deriva la conversación a una persona del equipo.

<img src="docs/capturas/04-derivacion.png" alt="Derivación" width="700">

### 5. Resistencia a manipulación

No revela sus instrucciones internas ni se desvía de su rol aunque se lo pidan directamente.

<img src="docs/capturas/05-seguridad.png" alt="Resistencia a manipulación" width="700">

## Qué hace

- Responde preguntas frecuentes de un negocio por WhatsApp, basándose únicamente en su información (horarios, productos, precios, domicilios, medios de pago).
- Si no sabe la respuesta, lo dice con honestidad y deriva la conversación a una persona del equipo.
- Está diseñado para no inventar datos: responde solo con la información del negocio y, si no la tiene, lo dice.
- Mantiene contexto de fecha, hora y festivos colombianos (por ejemplo, para calcular "mañana" o si un día es festivo).
- Recuerda el historial reciente de cada conversación.
- Evita procesar un mismo mensaje más de una vez si Meta lo reenvía.

## Cómo funciona

```mermaid
flowchart LR
    A[Usuario en WhatsApp] --> B[WhatsApp Cloud API de Meta]
    B --> C["Webhook Flask (/webhook)"]
    C --> D{"¿Firma X-Hub-Signature-256 válida?"}
    D -- No --> E["403 - se descarta"]
    D -- Sí --> F{"¿Mensaje ya procesado?"}
    F -- Sí --> G["200 - se ignora"]
    F -- No --> H[Cerebro]
    H --> I["Proveedor de IA (Claude)"]
    I --> H
    H --> J["Respuesta vía WhatsApp Cloud API"]
    J --> A
```

Cuando llega un mensaje, el webhook valida la firma del envío, descarta duplicados y notificaciones de estado (entregado/leído), y entrega el texto a `Cerebro`. `Cerebro` arma un prompt con la información del negocio y el contexto de fecha/festivos, se lo pasa al proveedor de IA configurado, valida que la respuesta venga en el formato esperado, y decide si responder directamente o derivar la conversación a una persona. Una vez validada la firma, el webhook responde rápido con `200` a Meta, incluso si el envío de la respuesta falla, para evitar reintentos innecesarios.

## Seguridad

- **Verificación de firma**: cada notificación de Meta se valida con HMAC-SHA256 (`X-Hub-Signature-256`) sobre el cuerpo crudo de la petición, usando `hmac.compare_digest`. Sin firma válida, la petición se descarta sin procesarse.
- **Secretos solo en `.env`**: nunca en el código ni en el repositorio. `.env.example` documenta qué variables hacen falta, sin valores.
- **Logs sin datos sensibles**: nunca se registran tokens, secretos ni firmas; los números de teléfono se enmascaran (solo se ven los últimos 4 dígitos); los fallos de firma distinguen "ausente" de "no coincide" sin exponer ningún valor.
- **Deduplicación de mensajes**: cada mensaje de Meta trae un ID único; si ya se procesó, se ignora.
- **Respuestas acotadas a la información del negocio**: el bot está instruido para responder solo con la información de `negocio.md`, y las pruebas verifican que derive cuando no la tiene.
- **Resistencia a manipulación del prompt**: instrucciones explícitas y validación de la respuesta reducen el riesgo de que el bot revele su configuración interna o se salga de su rol (ver captura de demostración).
- **Mensajes de error sin fugas de configuración**: un valor inválido en una variable de entorno nunca aparece en el mensaje de error ni en los logs.
- **Permisos reforzados para herramientas de IA**: este repositorio incluye una regla en `.claude/settings.json` que impide leer `.env` por accidente al trabajar con Claude Code.

## Tecnologías

- Python 3.12
- Flask (servidor del webhook)
- [Anthropic Claude](https://www.anthropic.com) como proveedor de IA (modelo configurable vía `.env`)
- WhatsApp Cloud API (Meta)
- SQLite (historial de conversación y deduplicación de mensajes)
- pytest (pruebas automáticas)
- `holidays` y `tzdata` (festivos colombianos y zona horaria `America/Bogota`)

## Diseño reutilizable

Este repositorio es un **núcleo genérico**, pensado para adaptarse a distintos negocios sin tocar la lógica central:

- La información del negocio vive en un archivo de perfil (ver "Perfiles de negocio" abajo): para un negocio nuevo, solo se agrega un archivo.
- Las credenciales y la configuración viven en `.env`: para un cliente nuevo, solo cambia ese archivo.
- El proveedor de IA está detrás de una interfaz común (`llm/base.py`): hoy usa Claude, y está preparado para agregar otros proveedores sin cambiar `cerebro.py` ni `webhook.py`.

### Perfiles de negocio

El webhook elige qué información de negocio usar según la variable `PERFIL_NEGOCIO`, contra una lista cerrada de perfiles conocidos:

| Valor | Archivo | Uso |
| --- | --- | --- |
| *(vacío, por defecto)* o `panaderia` | `negocio.md` | Demo del proyecto (Panadería San Roque). |
| `camilo` | `perfil_camilo.md` | Presenta el servicio de Camilo a dueños de negocio interesados en contratarlo. |

Un valor distinto a estos dos hace que el bot **falle al arrancar** con un mensaje claro, en vez de usar un perfil por defecto en silencio. Cada perfil nuevo requiere su propio despliegue (su propio número de WhatsApp), ya que un número solo puede atender un perfil a la vez.

## Estructura del proyecto

```
BotWhatsApp/
├── .env.example                   # Plantilla de variables de entorno (sin valores)
├── .claude/settings.json          # Regla de permisos: impide leer .env por accidente
├── requirements.txt
├── pytest.ini
├── negocio.md                     # Información del negocio (editable sin tocar código)
├── env.py                         # Helper para leer variables de entorno (con strip)
├── historial.py                   # Interfaz Historial + HistorialMemoria (para pruebas)
├── almacenamiento.py              # HistorialSQLite: historial y deduplicación de mensajes
├── llm/
│   ├── base.py                    # Interfaz ProveedorIA
│   ├── claude.py                  # Implementación con el SDK oficial de Anthropic
│   ├── openai_proveedor.py        # Placeholder para un futuro proveedor OpenAI
│   └── __init__.py                # Función fábrica según PROVEEDOR_IA
├── cerebro.py                     # Prompt, contexto de fecha/festivos, validación de respuesta
├── simulador.py                   # REPL de consola para probar sin WhatsApp
├── webhook.py                     # Servidor Flask: verificación, firma, deduplicación, envío
├── whatsapp.py                    # Envío de mensajes vía WhatsApp Cloud API
├── verificar_config.py            # Verifica que .env tenga las variables, sin exponer valores
├── verificar_suscripcion_waba.py  # Diagnóstico: apps suscritas a la cuenta de WhatsApp
├── suscribir_app_a_waba.py        # Suscribe esta app a la cuenta de WhatsApp
├── docs/capturas/                 # Capturas de pantalla de este README
└── tests/                         # Pruebas automáticas (pytest)
```

## Instalación y uso

En Windows (PowerShell):

```powershell
git clone <url-del-repositorio>
cd BotWhatsApp
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env         # Luego completa .env con tus propios valores
python verificar_config.py     # Confirma qué variables tienen valor, sin mostrarlas
python simulador.py            # Probar el "cerebro" del bot por consola, sin WhatsApp
python webhook.py              # Levantar el servidor del webhook
```

En Linux/macOS:

```bash
git clone <url-del-repositorio>
cd BotWhatsApp
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # Luego completa .env con tus propios valores
python verificar_config.py
python simulador.py
python webhook.py
```

Configuración del lado de Meta (resumen, sin IDs ni valores reales):

1. Crear una app en el panel de desarrolladores de Meta y agregar el producto de WhatsApp.
2. Obtener un número de prueba (o conectar un número propio) y su identificador.
3. En **Casos de uso → Conectarte con los clientes a través de WhatsApp → Configuración**, registrar la URL del webhook y el token de verificación, y suscribirse al campo `messages`.
4. Suscribir la app a la cuenta de WhatsApp Business (WABA) — sin esto, los mensajes reales no llegan al webhook aunque las pruebas del panel funcionen.
5. Para producción, generar un token de un usuario del sistema (con permisos de mensajería y administración de WhatsApp) en vez de usar el token temporal de prueba.

## Pruebas

```bash
pytest
```

El proyecto tiene **44 pruebas automáticas**, todas sin red real: simulan el proveedor de IA y el envío por WhatsApp, y usan bases de datos temporales para el historial y la deduplicación.

## Despliegue con Docker

Requisitos: Docker y Docker Compose instalados.

```bash
cp .env.example .env     # Completa .env con tus propios valores
docker compose up -d --build
```

Verificar que el servicio quedó arriba:

```bash
curl http://127.0.0.1:8000/salud   # Debe responder "ok"
docker compose ps                  # Debe mostrar "healthy"
```

Ver los logs:

```bash
docker compose logs -f bot-whatsapp
```

Actualizar tras un cambio de código:

```bash
docker compose up -d --build
```

El contenedor corre como usuario sin privilegios, con el sistema de archivos en modo solo lectura (salvo `/tmp` y el volumen de datos), y publica el puerto únicamente en `127.0.0.1` — para exponerlo a internet hace falta un proxy inverso con su propio dominio y TLS (no incluido aquí). La base de datos SQLite vive en un volumen nombrado de Docker, independiente del código de la imagen.

## Limitaciones y próximos pasos

- El túnel usado en desarrollo (Cloudflare Quick Tunnel) es temporal y cambia de URL en cada reinicio; en producción el webhook debe vivir en un servidor con dominio propio.
- La app de Meta sigue en modo desarrollo: los destinatarios están limitados a los números de prueba registrados.
- Posibles módulos futuros, sin tocar el núcleo: integración con un CRM en Google Sheets, recordatorios de pago, y un panel de administración para que el negocio edite su propia información.

## Autor

**Camilo Andrés Uribe Gaona** — Ingeniero de Sistemas, auditor interno ISO/IEC 27001:2022.

[LinkedIn](https://www.linkedin.com/in/camilo-uribe-gaona)

Desarrollado con apoyo de Claude Code.
