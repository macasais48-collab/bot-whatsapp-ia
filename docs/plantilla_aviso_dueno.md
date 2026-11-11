# Plantilla de WhatsApp para el aviso de pago al dueño

Este documento es genérico: no contiene datos de ningún negocio en particular. Sirve para cualquier perfil que use `NUMERO_DUENO` (pago asistido con QR de ejemplo).

## Por qué hace falta

El bot avisa al dueño cuando un cliente envía el comprobante de un pago (estado `pago_por_verificar`). Dentro de la ventana de 24 horas desde el último mensaje del dueño al bot, ese aviso se puede enviar como un mensaje libre. **Fuera de esa ventana, WhatsApp solo permite enviar una plantilla previamente aprobada por Meta.** Sin ella, el aviso simplemente no llega y el fallo queda silencioso (justo el problema que resuelve esta plantilla).

El bot usa siempre esta plantilla para el aviso principal (no solo como respaldo), para garantizar que llegue de inmediato sin depender de si el dueño escribió recientemente. Ver `CONTEXTO_BOT_WHATSAPP.md` para el detalle de por qué se eligió esta estrategia sobre la alternativa de "intentar primero el mensaje libre".

## Cómo crearla

1. Entra a **Meta Business Suite → WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Completa los campos exactamente así:

| Campo | Valor |
| --- | --- |
| **Nombre** | `aviso_pago_pendiente_verificacion` (solo minúsculas, números y guion bajo — regla de Meta) |
| **Categoría** | Utilidad (Utility) |
| **Idioma** | Español (`es`). Si el desplegable ofrece una variante regional, puedes preferirla — usa el código exacto que te muestre ahí. |
| **Encabezado** | Ninguno (sin imagen ni texto de encabezado) |
| **Cuerpo** | `Pedido #{{1}}: recibimos un comprobante de pago por {{2}}. Antes de confirmar, verifique en su app de pagos que el dinero llegó con esa referencia.` |
| **Botones** | Dos botones de **respuesta rápida (quick reply)**, en este orden: `Pago recibido`, `No ha llegado` |

3. Cuando Meta pida valores de ejemplo para `{{1}}` y `{{2}}` (solo para la revisión, no se usan en producción): `{{1}}` → `123`, `{{2}}` → `$45.000`.
4. Envía a revisión y espera la aprobación de Meta (normalmente toma minutos a pocas horas).

### Por qué este texto cumple las reglas de Meta

- No empieza con una variable (empieza con el texto fijo `Pedido #`) ni termina con una variable (termina en `...con esa referencia.`).
- Las dos variables no quedan adyacentes entre sí.
- El texto fijo (~140 caracteres) supera ampliamente, en proporción, a lo que aportan las dos variables (un número de pedido y un total, unos pocos caracteres cada uno).
- No nombra ningún medio de pago en particular ("su app de pagos" es genérico), para que la misma plantilla sirva para cualquier negocio sin tener que crear una nueva por cada medio de pago que use.

### Por qué sin encabezado de imagen

Un encabezado de imagen obliga a enviar *siempre* una imagen en ese componente. El reenvío del comprobante del cliente puede fallar (ya es un caso real, manejado hoy con una caída a texto); si el encabezado fuera obligatorio, la plantilla completa fallaría justo cuando más se necesita que el aviso llegue. En vez de eso, el bot intenta mostrar el comprobante **aparte**, como un envío de mejor esfuerzo: si no llega (por ejemplo, por la misma ventana de 24 horas cerrada), no importa — el aviso principal con el pedido y el total ya quedó garantizado por la plantilla, y el propio cuerpo ya le pide al dueño verificar directamente en su app de pagos, que es la fuente real de verdad.

## Payload de los botones

El id/payload de cada botón lo decide el bot en cada envío (no se configura un texto fijo en el WhatsApp Manager — un botón de respuesta rápida de plantilla ya permite esto): `pago_recibido_<id_de_pedido>` y `pago_no_llego_<id_de_pedido>`.

## Qué poner en `.env` una vez aprobada

```
PLANTILLA_AVISO_DUENO_NOMBRE=aviso_pago_pendiente_verificacion
PLANTILLA_AVISO_DUENO_IDIOMA=es
```

(o el código de idioma exacto que hayas elegido en el WhatsApp Manager). Si cualquiera de las dos variables queda vacía, el bot usa el aviso libre de siempre (como si no estuvieran configuradas) — nunca falla el arranque por esto.

## Prueba en vivo

El envío real y la respuesta a los botones de la plantilla real los prueba quien tenga acceso al número de WhatsApp del negocio, una vez Meta la apruebe — igual que con el resto de integraciones de Meta de este proyecto.
