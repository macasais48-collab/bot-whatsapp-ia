# Plantilla de WhatsApp para el aviso de derivación al negocio

Genérico: no contiene datos de ningún negocio en particular. Sirve para cualquier perfil que use `NUMERO_DUENO`.

## Por qué hace falta

Cuando el bot no puede resolver algo (o el cliente pide hablar con una persona, o pide algo que el negocio atiende a mano, como agendar una cita), deriva la conversación: el cliente recibe el mensaje de derivación del perfil. Hasta ahora nadie del negocio se enteraba, porque con la WhatsApp Cloud API el número del bot no se puede abrir en la app de WhatsApp.

Desde la sub-fase 6a, cada derivación avisa al dueño con el teléfono del cliente y un resumen breve de lo que pide. Fuera de la ventana de 24 horas (si el dueño no le ha escrito al bot en el último día), una plantilla aprobada es la única forma garantizada de que el aviso llegue.

Es puramente informativa: no lleva botones, el dueño no tiene que responder nada al bot; contacta al cliente directamente.

## Cómo crearla

1. Entra a **Meta Business Suite → WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Completa los campos exactamente así:

| Campo | Valor |
| --- | --- |
| **Nombre** | `aviso_derivacion` (solo minúsculas, números y guion bajo — regla de Meta) |
| **Categoría** | Utilidad (Utility) |
| **Idioma** | Español. Usa la misma variante que las otras plantillas del negocio (por ejemplo Spanish (COL), código `es_CO`) y anota el código exacto que te muestre el desplegable. |
| **Encabezado** | Ninguno |
| **Cuerpo** | `Un cliente pidió hablar con una persona de su equipo a través del asistente de WhatsApp. Teléfono del cliente: {{1}}. Resumen de la solicitud: {{2}}. Por favor comuníquese con el cliente lo antes posible para atender su solicitud.` |
| **Botones** | Ninguno |

3. Valores de ejemplo para la revisión de Meta (solo para eso, nunca se usan en producción):

| Variable | Ejemplo |
| --- | --- |
| `{{1}}` | `573001112233` |
| `{{2}}` | `Quiere agendar una cita para su mascota, de preferencia el martes en la mañana.` |

4. Envía a revisión y espera la aprobación de Meta.

### Por qué este texto cumple las reglas de Meta

- No empieza con una variable (empieza con el texto fijo "Un cliente pidió hablar con una persona...") ni termina con una variable (termina en "...para atender su solicitud.").
- Las dos variables no quedan adyacentes: cada una está rodeada de texto fijo ("Teléfono del cliente:", "Resumen de la solicitud:"), y la plantilla tiene mucho más texto fijo que variables.
- Ninguna variable trae saltos de línea, tabulaciones ni más de cuatro espacios seguidos: el bot pasa el resumen de la IA a una sola línea saneada y lo recorta a 300 caracteres como máximo (si la IA no generó resumen, se envía un texto fijo: "Sin resumen disponible; contacte al cliente para saber qué necesita.").
- Sin botones ni contenido promocional: es un aviso transaccional (Utilidad).

## Cuántos avisos llegan

Como máximo **un aviso por cliente cada 30 minutos**: si una misma conversación deriva varias veces seguidas, el dueño recibe solo el primero, para que no se le llene el chat. Si el envío falla, no cuenta (la siguiente derivación vuelve a intentar).

El bot sigue respondiéndole al cliente después de derivar (todavía no existe un modo de "persona atendiendo" que lo silencie).

## Por qué el teléfono del cliente va completo (excepción deliberada)

Igual que en el aviso de pedido nuevo (`docs/plantilla_aviso_pedido_nuevo.md`): el negocio necesita poder llamar o escribirle al cliente. El número completo va solo en el **contenido** del aviso; en los logs el teléfono sigue enmascarado siempre, y el resumen de la solicitud nunca se registra en el log.

## Qué poner en `.env` una vez aprobada

```
PLANTILLA_AVISO_DERIVACION_NOMBRE=aviso_derivacion
PLANTILLA_AVISO_DERIVACION_IDIOMA=es_CO
```

(o el código de idioma exacto que hayas elegido). Si cualquiera de las dos queda vacía, el bot avisa al dueño con un mensaje libre (puede no llegar fuera de la ventana de 24 horas; ese fallo queda registrado como informativo por la lectura de statuses) — nunca falla el arranque por esto.
