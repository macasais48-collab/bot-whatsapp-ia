# Plantilla de WhatsApp para el aviso de cita nueva al negocio

Genérico: no contiene datos de ningún negocio en particular. Sirve para cualquier perfil con agenda de citas (sección `citas` en `recursos_<perfil>.json`) y `NUMERO_DUENO` configurada.

## Por qué hace falta

Cada vez que un cliente confirma una cita en la agenda del bot (sub-fase 7a), el dueño recibe un aviso con el número de la cita, la fecha y hora, los datos que dio el cliente y su teléfono. Fuera de la ventana de 24 horas (si el dueño no le escribió al bot en el último día), una plantilla aprobada es la única forma garantizada de que el aviso llegue. Sin la plantilla, el aviso sale como mensaje libre y puede no llegar.

Es puramente informativa: no lleva botones. Para ver las próximas citas, el dueño escribe **citas** en el chat del bot.

## Cómo crearla

1. Entra a **Meta Business Suite → WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Completa los campos exactamente así:

| Campo | Valor |
| --- | --- |
| **Nombre** | `aviso_cita_nueva` (solo minúsculas, números y guion bajo — regla de Meta) |
| **Categoría** | Utilidad (Utility) |
| **Idioma** | Español, la misma variante de las otras plantillas del negocio (por ejemplo Spanish (COL), código `es_CO`). |
| **Encabezado** | Ninguno |
| **Cuerpo** | `Se agendó una nueva cita en su negocio a través del asistente de WhatsApp. Número de cita: {{1}}. Fecha y hora: {{2}}. Datos de la cita: {{3}}. Teléfono del cliente: {{4}}. Puede escribir citas en este chat para ver las próximas citas agendadas.` |
| **Botones** | Ninguno |

3. Valores de ejemplo para la revisión de Meta (solo para eso, nunca se usan en producción):

| Variable | Ejemplo |
| --- | --- |
| `{{1}}` | `12` |
| `{{2}}` | `martes 24 de noviembre, 8:00 a.m.` |
| `{{3}}` | `Nombre: Ana Pérez; Mascota: Toby, perro; Motivo: vacunación anual` |
| `{{4}}` | `573001112233` |

4. Envía a revisión y espera la aprobación de Meta.

### Por qué este texto cumple las reglas de Meta

- No empieza ni termina con una variable, y ninguna variable queda junto a otra: cada una está rodeada de texto fijo ("Número de cita:", "Fecha y hora:", "Datos de la cita:", "Teléfono del cliente:").
- Ninguna variable trae saltos de línea, tabulaciones ni más de cuatro espacios seguidos: el bot arma los datos de la cita en una sola línea ("Etiqueta: valor; Etiqueta: valor"), saneada y recortada a 300 caracteres.
- Sin botones ni contenido promocional: es un aviso transaccional (Utilidad).

## Por qué el teléfono del cliente va completo (excepción deliberada)

Igual que en el aviso de pedido nuevo y el de derivación: el negocio necesita poder contactar al cliente. El número completo va solo en el **contenido** del aviso; en los logs el teléfono sigue enmascarado y los datos de la cita nunca se registran.

## Qué poner en `.env` una vez aprobada

```
PLANTILLA_AVISO_CITA_NOMBRE=aviso_cita_nueva
PLANTILLA_AVISO_CITA_IDIOMA=es_CO
```

(o el código de idioma exacto que hayas elegido). Si cualquiera de las dos queda vacía, el bot avisa al dueño con un mensaje libre — nunca falla el arranque por esto. Si Meta reporta que el aviso no se entregó, queda en el log como informativo (código 131047, ventana cerrada) o como advertencia (cualquier otro código), con el número de la cita.
