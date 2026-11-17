# Plantilla de WhatsApp para el aviso de estado del pedido al cliente

Genérico: no contiene datos de ningún negocio en particular. Sirve para cualquier perfil que tome pedidos por el bot.

## Por qué hace falta

Cuando el dueño avanza un pedido (escribe **pedidos**, toca el pedido y el botón del siguiente paso, o usa `gestionar_pedido.py estado avanzar`), el cliente recibe un aviso: su pedido va en camino, está listo para recoger o fue entregado. Sin plantilla ese aviso es un mensaje libre y solo llega si el cliente le escribió al bot en las últimas 24 horas. En un pedido para el día siguiente, la ventana ya está cerrada y el aviso no llega (Meta responde con el código 131047). Una plantilla aprobada llega siempre (sub-fase 7b.2).

Es puramente informativa: no lleva botones.

## Cómo crearla

1. Entra a **Meta Business Suite → WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Completa los campos exactamente así:

| Campo | Valor |
| --- | --- |
| **Nombre** | `estado_pedido` (solo minúsculas, números y guion bajo — regla de Meta) |
| **Categoría** | Utilidad (Utility) |
| **Idioma** | Español, la misma variante de las otras plantillas del negocio (por ejemplo Spanish (COL), código `es_CO`). |
| **Encabezado** | Ninguno |
| **Cuerpo** | `Hay una novedad en su pedido número {{1}}. Estado actual: {{2}}. Gracias por su compra.` |
| **Botones** | Ninguno |

3. Valores de ejemplo para la revisión de Meta (solo para eso, nunca se usan en producción):

| Variable | Ejemplo |
| --- | --- |
| `{{1}}` | `123` |
| `{{2}}` | `En camino` |

4. Envía a revisión y espera la aprobación de Meta.

Lo que recibe el cliente en cada paso:

| Paso | Mensaje |
| --- | --- |
| Domicilio, en camino | Hay una novedad en su pedido número 123. Estado actual: En camino. Gracias por su compra. |
| Recoger, listo | Hay una novedad en su pedido número 123. Estado actual: Listo para recoger. Gracias por su compra. |
| Entregado | Hay una novedad en su pedido número 123. Estado actual: Entregado. Gracias por su compra. |

### Por qué este texto cumple las reglas de Meta

- No empieza ni termina con una variable, y las dos variables están separadas por texto fijo.
- Ninguna variable trae saltos de línea, tabulaciones ni más de cuatro espacios seguidos: son el número del pedido y uno de tres estados fijos que arma el código ("En camino", "Listo para recoger", "Entregado"), nunca texto escrito por alguien.
- Los estados no terminan en punto, así que nunca queda un punto doble después de `{{2}}`.
- Sin datos personales, sin botones ni contenido promocional: es un aviso transaccional (Utilidad).

## Qué poner en `.env` una vez aprobada

```
PLANTILLA_ESTADO_PEDIDO_NOMBRE=estado_pedido
PLANTILLA_ESTADO_PEDIDO_IDIOMA=es_CO
```

(o el código de idioma exacto que hayas elegido). Después, `docker compose up -d --force-recreate` para que el contenedor lea los valores nuevos. Si cualquiera de las dos queda vacía, el aviso sale como mensaje libre, igual que antes; nunca falla el arranque por esto.

El aviso se registra igual con o sin plantilla: el cambio de estado queda aplicado aunque el aviso falle, y si Meta reporta que no se entregó, queda en el log con el número del pedido y el teléfono enmascarado (informativo con el código 131047; advertencia con cualquier otro).
