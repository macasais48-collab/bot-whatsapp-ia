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
| `tamales` | `perfil_tamales.md` | Demo para un negocio de tamales con domicilios (Tamales Tolimenses, ficticio). |

Un valor que no esté en esta tabla y tampoco siga la convención de perfiles de cliente (ver abajo) hace que el bot **falle al arrancar** con un mensaje claro, en vez de usar un perfil por defecto en silencio. Cada perfil nuevo requiere su propio despliegue (su propio número de WhatsApp), ya que un número solo puede atender un perfil a la vez.

#### Perfiles de cliente (demos privadas, nunca en git ni en la imagen)

Además de los perfiles de este repositorio, el bot puede cargar un perfil de cliente real (un prospecto, una demo privada) sin que su información entre nunca al control de versiones ni a la imagen Docker — el repositorio es público. El mecanismo es genérico, por convención, y no requiere tocar código para cada cliente nuevo:

- Si `PERFIL_NEGOCIO` no coincide con ninguno de los perfiles de la tabla, pero es una clave válida (solo minúsculas, números y guion bajo, hasta 40 caracteres), el bot busca `clientes/<clave>/perfil_<clave>.md` y `clientes/<clave>/recursos_<clave>.json`.
- La carpeta `clientes/` está en `.gitignore` y en `.dockerignore`: nunca se sube a GitHub ni se copia en el `Dockerfile`. Llega al contenedor solo a través de un volumen de **solo lectura** (`./clientes:/app/clientes:ro` en `docker-compose.yml`).
- Las imágenes de un perfil de cliente (por ejemplo, un QR de ejemplo reutilizado) deben vivir dentro de su propia carpeta `clientes/<clave>/`, nunca referenciadas con `../` hacia fuera.
- Si la clave no sigue el patrón permitido, o si la carpeta/los archivos no existen, el bot falla al arrancar con un mensaje claro (nunca con un error críptico de archivo no encontrado).
- Para alternar entre un perfil de cliente y uno de este repositorio, solo se cambia `PERFIL_NEGOCIO` en `.env` y se recrea el contenedor (`docker compose up -d`).

### Mensajes enriquecidos

Además de texto, el bot puede compartir ubicación nativa de WhatsApp y botones con enlace (`cta_url`), según lo que tenga configurado cada perfil. Estos recursos viven en un archivo JSON propio por perfil (`recursos_panaderia.json`, `recursos_camilo.json`) que funciona como **lista blanca**: coordenadas, dirección y enlaces aprobados, cada uno con una clave (por ejemplo `"mapa"`). Ese JSON se valida al arrancar (coordenadas en rango, URLs `https`, textos dentro de los límites de WhatsApp) y falla con un error claro si algo está mal, igual que `PERFIL_NEGOCIO`.

La IA solo puede referirse a esos recursos por su clave, dentro del campo opcional `"adjuntos"` de su respuesta JSON — nunca puede inventar una URL, coordenada, clave o imagen. Si pide una clave que no existe en el perfil activo, ese adjunto se descarta y se registra en el log, pero la respuesta de texto se envía igual, sin fallar.

Las imágenes también se validan al arrancar (archivo existente, formato JPEG/PNG, tamaño ≤5 MB) y se suben a Meta solo cuando hace falta: el `media id` resultante se guarda en un caché dentro del volumen de datos (no en el repositorio) con su fecha de subida, y se resube automáticamente cuando falta o tiene más de 25 días. Si la subida falla, se registra (tipo y código de error, nunca el token) y la respuesta de texto se envía igual.

El bot también puede enviar botones de respuesta rápida (hasta 3) y listas (hasta 10 filas), con los mismos límites de WhatsApp verificados contra su documentación oficial. Un conjunto de botones (`"botones"` en `recursos_<perfil>.json`) es lista blanca igual que el resto: la IA solo puede pedir `{"tipo": "botones", "clave": "<clave>"}`. El menú (`{"tipo": "menu"}`) es distinto: se arma **por código**, directamente desde `"catalogo"`, así que la IA nunca decide qué productos o precios aparecen ahí.

### Toma de pedidos

Cuando el cliente elige un producto del menú (o toca el botón "Hacer pedido"), la conversación entra a un **modo de pedido determinista**: a partir de ahí, cada mensaje lo maneja `flujo_pedido.py` por código — `cerebro.py` (la IA) deja de participar por completo hasta que el pedido se confirma, se cancela o se agota el tiempo. Esto es intencional: un pedido con dinero de por medio no puede depender de que la IA calcule ni redondee nada.

El flujo cubre, en orden: elegir productos (con botones "Agregar otro"/"Continuar" para pedir varios) → tipo de entrega (domicilio o recoger en el local). Si es domicilio: valida el pedido mínimo, **solo entonces** pide el consentimiento de datos (Ley 1581) — recoger en el local nunca lo pide, porque no hace falta guardar ninguna dirección — y si el cliente no acepta, no cancela: ofrece `[Recoger en el local] [Cancelar]` en su lugar. Si acepta, sigue con la zona (de una lista) y la dirección (por texto o compartiendo la ubicación). El resumen y el mensaje final de confirmación muestran la zona y la dirección exactas (o "ubicación compartida por WhatsApp" si el cliente compartió su ubicación en vez de escribirla), con el total **siempre calculado desde `"catalogo"` y `"domicilio"`**. También maneja salidas en cualquier punto: palabras clave para cancelar o pedir una persona (sin distinguir mayúsculas ni tildes), 30 minutos sin respuesta cancelan el pedido en construcción, y ante una entrada que no se reconoce reenvía el mismo paso (los mismos botones, la misma lista o el mismo resumen) en vez de un mensaje genérico, para que el cliente no pierda lo ya elegido.

Los pedidos se guardan en la misma base SQLite (`pedidos.py`, tablas `pedidos` y `pedido_items`), con un número de pedido autoincremental y un solo pedido activo por número de cliente (en construcción, con el pago pendiente, o con el pago en verificación).

### Pago asistido

Al tocar "Confirmar", el bot pregunta cómo desea pagar: **efectivo** (el pedido queda confirmado de inmediato, con pago contra entrega o al recoger) o **QR / transferencia** (envía la imagen del QR de ejemplo con el valor exacto y el número de pedido como referencia, y pide el comprobante). El valor a pagar siempre sale del total ya calculado por código — nunca de la IA ni de un texto del cliente.

Cuando el cliente envía la foto del comprobante, el pedido pasa a verificación y, si está configurada la variable `NUMERO_DUENO`, el bot avisa al dueño con botones `[Pago recibido] [No ha llegado]`. Solo un mensaje que llegue exactamente de ese número puede confirmar o rechazar un pago; cualquier otro mensaje del dueño (un "hola", un botón que ya no aplica) recibe un recordatorio fijo de que ese es el número del negocio, sin pasar nunca por la IA ni por el flujo de pedidos. El botón se acepta en los dos formatos que WhatsApp puede entregar: un mensaje interactivo libre o la respuesta a una plantilla (ver abajo) — mismas validaciones en ambos casos.

**Aviso al dueño siempre por plantilla**: si además de `NUMERO_DUENO` están configuradas `PLANTILLA_AVISO_DUENO_NOMBRE` y `PLANTILLA_AVISO_DUENO_IDIOMA` (una plantilla de WhatsApp aprobada por Meta — ver `docs/plantilla_aviso_dueno.md` para la especificación exacta y cómo crearla en el WhatsApp Manager), el aviso principal se envía **siempre** por esa plantilla, con el número de pedido y el total como variables: es el único canal garantizado fuera de la ventana de 24 horas, así que no depende de que el dueño le haya escrito al bot recientemente. El comprobante del cliente (reenviado — descargado y vuelto a subir en memoria, sin escribir nada a disco ni a la base de datos; la documentación oficial de Meta no ofrece una forma de reenviar un media id entrante directamente) se intenta mostrar **aparte**, como un envío de mejor esfuerzo: si falla, no afecta el aviso principal, que ya quedó garantizado. Si cualquiera de las dos variables de la plantilla no está configurada, el bot usa el mensaje libre de siempre (texto o imagen + botones), exactamente igual que antes de que existiera esta plantilla.

**Statuses del webhook**: el bot ahora lee las notificaciones de estado que manda Meta (`sent`/`delivered`/`read`/`failed`) — las tres primeras nunca generan ningún log; un `failed` se registra con el código y el título del error de Meta, el teléfono enmascarado, y el número de pedido si el mensaje que falló era un aviso al dueño (asociado por el id de mensaje, `wamid`, en una tabla mínima sin contenido ni datos personales). Si el que falla es el envío aparte del comprobante (mejor esfuerzo), el log es informativo, no una advertencia, y nunca aparece como "pedido desconocido".

**Aviso de pedido nuevo al negocio**: cada vez que un pedido queda confirmado —en efectivo, incluido desde el botón `[Pagar en efectivo]` en pago pendiente, o por QR cuando el dueño o `gestionar_pedido.py` confirman el pago— y `NUMERO_DUENO` está configurada, el bot avisa al dueño con el número de pedido, los productos, el total, la forma de entrega (zona y dirección), el método de pago y el **teléfono completo del cliente**. Esta es una excepción deliberada, solo para que el negocio pueda contactarlo y coordinar la entrega: en los logs el teléfono siempre sigue enmascarado, sin ninguna excepción. Si además están configuradas `PLANTILLA_AVISO_PEDIDO_NUEVO_NOMBRE` y `PLANTILLA_AVISO_PEDIDO_NUEVO_IDIOMA` (otra plantilla de WhatsApp aprobada por Meta, sin botones — ver `docs/plantilla_aviso_pedido_nuevo.md` para la especificación exacta y cómo crearla en el WhatsApp Manager), el aviso se envía **siempre** por esa plantilla, igual de garantizado fuera de la ventana de 24 horas que el aviso de pago. Si cualquiera de las dos variables no está configurada, el bot usa un mensaje de texto libre (puede fallar fuera de la ventana de 24 horas, como cualquier mensaje libre — ese fallo ya queda registrado por la lectura de statuses).

Como respaldo (o si `NUMERO_DUENO` no está configurada), `gestionar_pedido.py` permite listar los pedidos en espera y confirmar o rechazar un pago desde la línea de comandos dentro del contenedor:

```bash
docker compose exec bot-whatsapp python gestionar_pedido.py listar
docker compose exec bot-whatsapp python gestionar_pedido.py confirmar <numero_de_pedido>
docker compose exec bot-whatsapp python gestionar_pedido.py no-llego <numero_de_pedido>
```

El script enmascara siempre el teléfono del cliente y pide una confirmación explícita antes de aplicar el cambio. Las palabras clave para cancelar o pedir una persona siguen funcionando durante el pago, salvo que ya se envió un comprobante: ahí "cancelar" ya no cancela (hay dinero en camino) y, junto con "asesor", solo deriva a una persona sin tocar el estado del pedido. El timeout de 30 minutos tampoco aplica mientras se espera un pago.

### Estados del pedido

Un pedido confirmado (en efectivo o con el pago por QR ya verificado) queda **en preparación**, y desde ahí avanza un paso a la vez: a domicilio, *en preparación → en camino → entregado*; para recoger, *en preparación → listo para recoger → entregado*. El estado de entrega se guarda en una columna aparte (`estado_entrega`), sin tocar el estado de pago.

El dueño escribe **pedidos** (sin importar mayúsculas ni tildes) desde `NUMERO_DUENO` y recibe una lista de los pedidos activos, del más antiguo al más reciente, con el número de pedido, la forma de entrega, el estado y el total (sin teléfono ni dirección). Si hay más de 10, se muestran 9 y una fila "Ver más" con los siguientes. Al tocar un pedido, recibe su detalle y **un solo botón** con el siguiente paso válido (p. ej. "Marcar en camino"). Al tocarlo, el cliente recibe un aviso corto en texto libre ("Su pedido #N va en camino.") y el dueño una confirmación. El botón lleva el número de pedido y el paso exacto, así que una doble pulsación o un botón viejo nunca aplica un cambio que ya no corresponde ni repite el aviso al cliente.

El aviso al cliente es un mensaje libre: en este tipo de negocio la ventana de 24 horas suele estar abierta, porque el cliente acaba de escribir para hacer el pedido. Si está cerrada, Meta lo rechaza con el código 131047; el cambio de estado igual queda aplicado y el fallo se registra en el log como informativo, asociado al pedido.

Los pedidos que ya estaban confirmados antes de existir esta función se migran como **entregados**, para que no aparezcan como pendientes.

Respaldo desde la línea de comandos:

```bash
docker compose exec bot-whatsapp python gestionar_pedido.py estado listar
docker compose exec bot-whatsapp python gestionar_pedido.py estado avanzar <numero_de_pedido>
```

Igual que los comandos de pago, el script enmascara el teléfono del cliente y pide confirmación explícita antes de aplicar el cambio.

**Logging bajo gunicorn:** `gunicorn.conf.py` (cargado con `--config` desde el `CMD` del Dockerfile) configura el logging en cada worker (`post_fork`), para que los eventos de `webhook.py`, `flujo_pedido.py` y `pago_pedido.py` (p. ej. "Pedido #7 confirmado", "mensaje antiguo ignorado") se vean con `docker compose logs`. El log de accesos propio de gunicorn está desactivado para no duplicar la línea que ya registra `webhook.py` por cada petición (método, ruta sin cadena de consulta, código de estado) — esa línea nunca incluye el verify token de Meta, y las peticiones a `/salud` del healthcheck no se registran. Los eventos de la aplicación nunca incluyen el número de teléfono completo (solo los últimos 4 dígitos, vía `telefono.py`), el texto de los mensajes, direcciones, ubicaciones ni el contenido de un comprobante de pago — solo el hecho de que algo pasó.

### Créditos de fotos

| Archivo | Crédito |
| --- | --- |
| `tortas2.jpg` | Foto de Unsplash (licencia Unsplash) |

Estas son fotos de demostración, de uso libre, elegidas solo para mostrar la funcionalidad. En un despliegue real para un cliente, se reemplazan por fotos propias del negocio (su pan, sus tortas, su vitrina), definidas en su propio `recursos_<perfil>.json`.

Claves de imagen propuestas para cuando el negocio tenga sus propias fotos: `pandebono`, `almojabana`, `pan_rollo` (o `pan_alinado`), `roscon`, `torta_chocolate` (en uso), `tres_leches`, `vitrina` y `pan_del_dia`.

`recursos/demo/qr_ejemplo.png` (perfil `tamales`) no es una foto: es una imagen generada con Pillow para la demo, con el texto "QR DE EJEMPLO - NO PAGAR" bien visible. Nunca se usa un QR de pago real (ni de Bold ni de ningún otro medio) en este repositorio.

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
├── basedatos.py                   # Conexión SQLite compartida: WAL, busy_timeout y reintentos ante bloqueo
├── almacenamiento.py              # HistorialSQLite: historial y deduplicación de mensajes
├── llm/
│   ├── base.py                    # Interfaz ProveedorIA
│   ├── claude.py                  # Implementación con el SDK oficial de Anthropic
│   ├── openai_proveedor.py        # Placeholder para un futuro proveedor OpenAI
│   └── __init__.py                # Función fábrica según PROVEEDOR_IA
├── cerebro.py                     # Prompt, contexto de fecha/festivos, validación de respuesta
├── recursos.py                    # Valida el JSON de recursos (ubicación, enlaces, catálogo...) de cada perfil
├── recursos_panaderia.json        # Lista blanca de recursos del perfil "panaderia"
├── recursos_camilo.json           # Lista blanca de recursos del perfil "camilo"
├── recursos_tamales.json          # Lista blanca de recursos del perfil "tamales"
├── perfil_camilo.md               # Información del perfil "camilo"
├── perfil_tamales.md              # Información del perfil "tamales"
├── simulador.py                   # REPL de consola para probar sin WhatsApp
├── webhook.py                     # Servidor Flask: verificación, firma, deduplicación, envío
├── whatsapp.py                    # Envío de mensajes de texto vía WhatsApp Cloud API
├── mensajes_enriquecidos.py       # Envío de ubicación, botón con enlace (cta_url), imágenes, botones y listas
├── media_cache.py                 # Sube imágenes a Meta y cachea su media id (vence a los 25 días)
├── red_meta.py                     # Reintentos compartidos ante 429/error de conexión con la Graph API
├── pedidos.py                     # Persistencia de pedidos en SQLite (tablas pedidos y pedido_items)
├── pedido_resumen.py               # Resumen del pedido: versión multilínea y versiones de una línea para plantillas
├── perfiles_negocio.py             # Resolución de perfil/recursos activos (sin Flask; usado por webhook.py y gestionar_pedido.py)
├── flujo_pedido.py                # Máquina de estados de la toma de pedidos y el pago (sin IA, sin Flask)
├── pago_pedido.py                 # Confirmar/rechazar un pago y avisar al dueño de un pedido nuevo (compartido webhook/script)
├── estado_pedido.py               # Estados de entrega del pedido: lista del dueño, botón del siguiente paso, aviso al cliente
├── gestionar_pedido.py             # CLI de respaldo: pagos y estados de entrega dentro del contenedor
├── telefono.py                    # Enmascarado/normalización de número de teléfono
├── gunicorn.conf.py                # Logging de gunicorn (stdout; accesslog propio desactivado)
├── verificar_config.py            # Verifica que .env tenga las variables, sin exponer valores
├── verificar_suscripcion_waba.py  # Diagnóstico: apps suscritas a la cuenta de WhatsApp
├── suscribir_app_a_waba.py        # Suscribe esta app a la cuenta de WhatsApp
├── docs/capturas/                 # Capturas de pantalla de este README
├── docs/plantilla_aviso_dueno.md  # Especificación de la plantilla del aviso al dueño (WhatsApp Manager)
├── docs/plantilla_aviso_pedido_nuevo.md  # Especificación de la plantilla del aviso de pedido nuevo (WhatsApp Manager)
├── tests/                         # Pruebas automáticas (pytest)
├── tests/carga/                   # Prueba de carga aparte (no es parte de la suite de pytest)
└── clientes/<clave>/              # Perfiles de cliente privados (fuera de git y de la imagen; ver "Perfiles de cliente")
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

El proyecto tiene **283 pruebas automáticas** (una se omite en Windows sin privilegios de administrador: una prueba de defensa contra enlaces simbólicos), todas sin red real: simulan el proveedor de IA y el envío por WhatsApp, y usan bases de datos temporales para el historial, la deduplicación y los pedidos.

## Rendimiento

El servidor corre con gunicorn en un solo proceso y un pool de **12 hilos** (`--worker-class gthread --workers 1 --threads 12 --timeout 60`), con SQLite en modo **WAL** (lectores concurrentes sin bloquear al escritor) y reintentos cortos ante "database is locked" o ante un 429/error de conexión al enviar a WhatsApp (nunca ante un timeout, para no duplicar un mensaje que Meta ya pudo haber procesado).

Con esa configuración, una prueba de carga local con 20 pedidos completos simultáneos (elegir producto, cantidad, entrega, confirmar y pagar) tardó en promedio **5.7 s** por pedido (máximo 6.1 s), sin errores, sin mensajes perdidos y sin que ningún pedido se mezclara con otro; con 50 pedidos simultáneos, el promedio sube a **11.8 s** (máximo 13.6 s) — la configuración actual sostiene con comodidad el tráfico esperado de un negocio (varios clientes a la vez), pero una ráfaga de 50 pedidos en el mismo instante ya no cumple el objetivo de menos de 5 segundos por pedido; ver `CONTEXTO_BOT_WHATSAPP.md` para el detalle completo y las mejoras que quedan pendientes para esa escala mayor.

Cómo correr la prueba de carga (nunca llama a Meta ni a Anthropic de verdad; usa fakes con retraso configurable, un secreto HMAC de prueba, números ficticios y una base de datos temporal — ver `tests/carga/`):

```bash
./venv/Scripts/python.exe -m pip install -r requirements-carga.txt   # solo la primera vez
./venv/Scripts/python.exe tests/carga/correr_carga.py --clientes 20
./venv/Scripts/python.exe tests/carga/correr_carga.py --clientes 50 --hilos 12
```

`requirements-carga.txt` (solo `waitress`, el servidor que usa el servidor de prueba) es una dependencia de desarrollo aparte: nunca entra a la imagen de producción, que solo instala `requirements.txt`.

En Windows no se puede usar gunicorn para este servidor de prueba (depende de `fcntl`, que no existe fuera de Unix); en su lugar se usa `waitress`, que sirve con el mismo modelo de concurrencia (un proceso, un pool de hilos de tamaño configurable). El resultado de cada corrida se guarda como JSON en `tests/carga/resultados/` (fuera de git).

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
