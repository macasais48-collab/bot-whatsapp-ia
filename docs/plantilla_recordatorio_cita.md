# Plantilla de WhatsApp para el recordatorio de cita al cliente

Genérico: no contiene datos de ningún negocio en particular. Sirve para cualquier perfil con agenda de citas (sección `citas` en `recursos_<perfil>.json`).

## Por qué hace falta

Antes de cada cita confirmada (24 horas por defecto, configurable con `recordatorio_horas` en la sección `citas`; `0` los desactiva), el bot le recuerda la cita al cliente (sub-fase 7b.1). Lo normal es que en ese momento el cliente no le haya escrito al bot en las últimas 24 horas, así que la ventana de conversación está cerrada: una plantilla aprobada es la única forma garantizada de que el recordatorio llegue. Sin la plantilla, sale como mensaje libre y solo llega si la ventana sigue abierta.

Es puramente informativa: no lleva botones. Si el cliente necesita cambiar o cancelar, escribe **asesor** y el bot deriva la conversación a una persona del equipo (con aviso al negocio).

## Cómo crearla

1. Entra a **Meta Business Suite → WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Completa los campos exactamente así:

| Campo | Valor |
| --- | --- |
| **Nombre** | `recordatorio_cita` (solo minúsculas, números y guion bajo — regla de Meta) |
| **Categoría** | Utilidad (Utility) |
| **Idioma** | Español, la misma variante de las otras plantillas del negocio (por ejemplo Spanish (COL), código `es_CO`). |
| **Encabezado** | Ninguno |
| **Cuerpo** | `Le recordamos su cita número {{1}}, agendada para el {{2}}. Si necesita cambiarla o cancelarla, escriba asesor en este chat y una persona del equipo le ayudará.` |
| **Botones** | Ninguno |

3. Valores de ejemplo para la revisión de Meta (solo para eso, nunca se usan en producción):

| Variable | Ejemplo |
| --- | --- |
| `{{1}}` | `12` |
| `{{2}}` | `martes 24 de noviembre, 8:00 a.m` |

4. Envía a revisión y espera la aprobación de Meta.

El mensaje que recibe el cliente queda así:

> Le recordamos su cita número 12, agendada para el martes 24 de noviembre, 8:00 a.m. Si necesita cambiarla o cancelarla, escriba asesor en este chat y una persona del equipo le ayudará.

### Por qué este texto cumple las reglas de Meta

- No empieza ni termina con una variable, y las dos variables están separadas por texto fijo.
- Ninguna variable trae saltos de línea, tabulaciones ni más de cuatro espacios seguidos: el número de cita y la fecha son de una sola línea.
- El bot envía la fecha **sin** su punto final ("8:00 a.m"), porque el texto fijo de la plantilla ya pone el punto después de `{{2}}`: así el cliente ve "8:00 a.m." y no "8:00 a.m..".
- No lleva datos personales (ni nombre ni motivo): solo el número y la fecha de la cita.
- Sin botones ni contenido promocional: es un mensaje transaccional (Utilidad).

## Qué poner en `.env` una vez aprobada

```
PLANTILLA_RECORDATORIO_CITA_NOMBRE=recordatorio_cita
PLANTILLA_RECORDATORIO_CITA_IDIOMA=es_CO
```

(o el código de idioma exacto que hayas elegido). Después, `docker compose up -d --force-recreate` para que el contenedor lea los valores nuevos. Si cualquiera de las dos queda vacía, el recordatorio sale como mensaje libre; nunca falla el arranque por esto.

## Cómo se comporta

- Revisa cada 15 minutos (y una vez al arrancar). Cada cita recibe un solo recordatorio: la marca se guarda en la cita antes de enviarlo.
- Nunca se envía para citas canceladas o ya pasadas, ni si falta menos de 30 minutos para la cita (por ejemplo, si el bot estuvo apagado a la hora del recordatorio).
- Una cita agendada cuando ya faltaba menos de `recordatorio_horas` no recibe recordatorio: el cliente acaba de recibir la confirmación con la fecha y la hora.
- Si Meta no acepta el envío, se reintenta en la siguiente revisión. Si Meta reporta después que no se entregó, queda en el log como informativo (código 131047, ventana cerrada) o como advertencia (cualquier otro código), con el número de la cita y el teléfono enmascarado.
