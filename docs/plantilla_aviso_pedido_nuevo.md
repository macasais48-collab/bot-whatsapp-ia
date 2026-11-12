# Plantilla de WhatsApp para el aviso de pedido nuevo al negocio

Genérico: no contiene datos de ningún negocio en particular. Sirve para cualquier perfil que use `NUMERO_DUENO`.

## Por qué hace falta

Hoy, cuando un pedido se confirma en efectivo, el negocio no recibe ningún aviso — solo se entera cuando hay un comprobante de QR por verificar. Esta plantilla cierra ese vacío: avisa al dueño en los dos momentos en que un pedido queda confirmado (efectivo o QR pagado), siempre, sin depender de si el dueño le escribió recientemente al bot (fuera de la ventana de 24 horas, una plantilla aprobada es la única forma garantizada de que el aviso llegue — ver también `docs/plantilla_aviso_dueno.md` para el mismo criterio aplicado al aviso de verificación de pago).

A diferencia de esa otra plantilla, esta es puramente informativa: no lleva botones, el dueño no tiene que responder nada.

## Cómo crearla

1. Entra a **Meta Business Suite → WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Completa los campos exactamente así:

| Campo | Valor |
| --- | --- |
| **Nombre** | `aviso_pedido_nuevo` (solo minúsculas, números y guion bajo — regla de Meta) |
| **Categoría** | Utilidad (Utility) |
| **Idioma** | Español (`es`). Si el desplegable ofrece una variante regional, puedes preferirla — usa el código exacto que te muestre ahí. |
| **Encabezado** | Ninguno |
| **Cuerpo** | `Tiene un nuevo pedido confirmado en su negocio. Número de pedido: {{1}}. Productos: {{2}}. Valor total del pedido: {{3}}. Forma de entrega: {{4}}. Método de pago: {{5}}. Teléfono del cliente: {{6}}. Puede contactarlo para coordinar la entrega o resolver cualquier duda sobre el pedido.` |
| **Botones** | Ninguno |

3. Valores de ejemplo para la revisión de Meta (solo para eso, nunca se usan en producción):

| Variable | Ejemplo |
| --- | --- |
| `{{1}}` | `123` |
| `{{2}}` | `2 x Producto especial, 1 x Bebida` |
| `{{3}}` | `$45.000` |
| `{{4}}` | `Domicilio - Centro, Calle 10 #5-23` |
| `{{5}}` | `Efectivo` |
| `{{6}}` | `573001112233` |

4. Envía a revisión y espera la aprobación de Meta.

### Por qué este texto cumple las reglas de Meta

- No empieza con una variable (empieza con el texto fijo "Tiene un nuevo pedido confirmado en su negocio.") ni termina con una variable (termina en el texto fijo "...o resolver cualquier duda sobre el pedido.").
- Ninguna variable queda adyacente a otra: cada una está rodeada de bastante texto fijo ("Número de pedido:", "Productos:", "Valor total del pedido:", "Forma de entrega:", "Método de pago:", "Teléfono del cliente:"), precisamente para que Meta la apruebe con más facilidad (las plantillas con muchas variables y poco texto fijo alrededor suelen ser rechazadas).
- Ninguna variable trae saltos de línea, tabulaciones ni más de cuatro espacios seguidos: el bot arma los productos y la forma de entrega en una sola línea (recortándolos si son muy largos) y sanea cualquier texto del cliente (por ejemplo, su dirección) antes de ponerlo en una variable.

## Por qué el teléfono del cliente va completo (excepción deliberada)

En todos los demás avisos de este proyecto, el teléfono del cliente se enmascara (solo los últimos 4 dígitos). Aquí no: el negocio necesita poder llamar o escribirle al cliente directamente para coordinar la entrega, confirmar una dirección o resolver una duda — enmascararlo le quitaría la utilidad al aviso. Es la única notificación del proyecto que muestra el número completo, y solo dentro del **contenido** de este aviso: en los logs, el teléfono del cliente sigue enmascarado siempre, sin excepción.

## Qué poner en `.env` una vez aprobada

```
PLANTILLA_AVISO_PEDIDO_NUEVO_NOMBRE=aviso_pedido_nuevo
PLANTILLA_AVISO_PEDIDO_NUEVO_IDIOMA=es
```

(o el código de idioma exacto que hayas elegido). Si cualquiera de las dos queda vacía, el bot avisa al dueño con un mensaje libre de siempre (puede no llegar fuera de la ventana de 24 horas; ese fallo queda registrado por la lectura de statuses ya existente) — nunca falla el arranque por esto.
