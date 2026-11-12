# Plantilla de WhatsApp para el reporte semanal al negocio

Este documento es genérico: no tiene datos de ningún negocio en particular y sirve para cualquier perfil que use `NUMERO_DUENO`.

## Por qué hace falta

Cada semana, el día y la hora configurados (por defecto el lunes a las 8:00, hora de Bogotá), el bot envía al dueño un reporte con las cifras de la última semana completa, de lunes a domingo.

Si nadie del negocio le escribió al bot en las últimas 24 horas, un mensaje libre no llega. Meta lo rechaza con un error, que el bot registra en el log como informativo. Con esta plantilla aprobada, el reporte llega siempre, igual que los avisos de pago y de pedido nuevo (ver `docs/plantilla_aviso_dueno.md` y `docs/plantilla_aviso_pedido_nuevo.md`).

La plantilla solo informa: no lleva botones y el dueño no tiene que responder nada. Para ver las cifras de la semana en curso, el dueño puede escribir **reporte** en cualquier momento; esa respuesta es un mensaje libre y no usa esta plantilla.

## Cómo crearla

1. Entre a **Meta Business Suite → WhatsApp Manager → Plantillas de mensajes → Crear plantilla**.
2. Complete los campos exactamente así:

| Campo | Valor |
| --- | --- |
| **Nombre** | `reporte_semanal` (solo minúsculas, números y guion bajo: regla de Meta) |
| **Categoría** | Utilidad (Utility) |
| **Idioma** | Español (`es`). Si el desplegable ofrece una variante regional, puede elegirla; use el código exacto que muestre ahí. |
| **Encabezado** | Ninguno |
| **Cuerpo** | `Este es el reporte semanal de su negocio, del {{1}}. Pedidos confirmados en la semana: {{2}}. Ventas totales de la semana: {{3}}. Detalle por método de pago: {{4}}. Detalle por forma de entrega: {{5}}. Productos más vendidos: {{6}}. Estado de las entregas: {{7}}. Puede escribir reporte en este chat para ver las cifras de la semana en curso.` |
| **Botones** | Ninguno |

3. Use estos valores de ejemplo para la revisión de Meta. Solo sirven para eso; el bot nunca los envía.

| Variable | Qué contiene | Ejemplo |
| --- | --- | --- |
| `{{1}}` | Rango de fechas de la semana | `02/11/2026 al 08/11/2026` |
| `{{2}}` | Número de pedidos confirmados | `12` |
| `{{3}}` | Ventas totales | `$240.000` |
| `{{4}}` | Pedidos y ventas por método de pago | `Efectivo 7 ($130.000), QR / transferencia 5 ($110.000)` |
| `{{5}}` | Pedidos por forma de entrega | `Domicilio 8, Recoger en el local 4` |
| `{{6}}` | Los 3 productos más vendidos (unidades) | `15 x Producto A, 9 x Producto B, 4 x Producto C` |
| `{{7}}` | Entregados y pendientes | `11 entregados y 1 pendiente` |

4. Envíela a revisión y espere la aprobación de Meta.

### Por qué este texto cumple las reglas de Meta

- **No empieza ni termina con una variable.** Empieza con el texto fijo "Este es el reporte semanal de su negocio" y termina con "...las cifras de la semana en curso."
- **Ninguna variable queda junto a otra.** Cada una tiene texto fijo descriptivo alrededor ("Pedidos confirmados en la semana:", "Ventas totales de la semana:", etc.). Meta suele rechazar las plantillas con muchas variables y poco texto fijo.
- **Ninguna variable trae saltos de línea, tabulaciones ni más de cuatro espacios seguidos.** El bot arma cada desglose en una sola línea y la sanea antes de enviarla.
- **Ninguna variable va vacía.** Una semana sin ventas se envía igual, con `0`, `$0` y `ninguno` en los desgloses.
- **No hay datos personales.** La plantilla nunca lleva teléfonos, nombres ni direcciones de clientes, solo cifras agregadas y nombres de productos del catálogo.

## Qué poner en `.env` una vez aprobada

```
PLANTILLA_REPORTE_SEMANAL_NOMBRE=reporte_semanal
PLANTILLA_REPORTE_SEMANAL_IDIOMA=es
```

O el código de idioma exacto que haya elegido. Si cualquiera de las dos variables queda vacía, el bot envía el reporte automático como mensaje libre, que puede no llegar si la ventana de 24 horas está cerrada. El arranque del bot nunca falla por esto.

Para cambiar el día o la hora del envío automático (opcional):

```
REPORTE_SEMANAL_DIA=lunes
REPORTE_SEMANAL_HORA=08:00
```

Valores válidos:
- **Día:** de lunes a domingo, con o sin tildes.
- **Hora:** formato de 24 horas, en hora de Bogotá.

El reporte siempre cubre la última semana completa (de lunes a domingo) anterior al envío. Por eso conviene programarlo el lunes: con un día posterior, el reporte llega con más días de retraso.
