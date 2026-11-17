# Plantilla de perfil para un cliente nuevo

Plantilla genérica (sin datos de ningún negocio) para montar el perfil de un cliente nuevo a partir de la ficha de levantamiento de la visita. El perfil del cliente **nunca** se versiona: vive en `clientes/<clave>/` (ignorado por git y por Docker) y llega al servidor por `scp`.

| Archivo | Para qué |
| --- | --- |
| `perfil_PLANTILLA.md` | Lo que el asistente sabe y cómo se comporta: identidad, trato, horario, servicios, productos con descripción, domicilios, pagos, reglas del rubro, citas, preguntas frecuentes y mensaje de derivación. |
| `recursos_PLANTILLA.json` | Lo que el motor valida y usa por código: ubicación y mapa, QR, catálogo para pedidos, zonas de domicilio y botones de bienvenida. |

Convención: todo lo que está entre corchetes en MAYÚSCULAS (`[NOMBRE DEL NEGOCIO]`, `[HORARIO]`, …) o marcado `EJEMPLO` se reemplaza o se borra. Las instrucciones entre corchetes también se borran: el asistente lee el archivo completo.

## 1. Elegir la clave del cliente

- Solo minúsculas, números y guion bajo, hasta 40 caracteres (por ejemplo `panaderia_centro`).
- No puede ser `panaderia`, `camilo` ni `tamales` (perfiles del repositorio).
- La clave define los nombres de archivo: `clientes/<clave>/perfil_<clave>.md` y `clientes/<clave>/recursos_<clave>.json`.

## 2. Copiar la plantilla (PC, PowerShell en modo normal, en `C:\Users\Camilo\BotWhatsApp`)

```powershell
$clave = 'mi_cliente'   # cámbiela por la clave elegida
New-Item -ItemType Directory -Force "clientes\$clave" | Out-Null
Copy-Item plantillas_perfil\perfil_PLANTILLA.md "clientes\$clave\perfil_$clave.md"
Copy-Item plantillas_perfil\recursos_PLANTILLA.json "clientes\$clave\recursos_$clave.json"
Copy-Item recursos\demo\qr_ejemplo.png "clientes\$clave\qr_ejemplo.png"
```

El QR copiado es el de ejemplo ("QR DE EJEMPLO - NO PAGAR"): úselo para demos. Para un cliente real que ya contrató, reemplace `qr_ejemplo.png` por la imagen del QR del negocio (JPG o PNG, máximo 5 MB) y ajuste su `descripcion`; la clave `qr_ejemplo` se conserva, porque es la que busca el sistema de pedidos.

## 3. Llenar el perfil (`perfil_<clave>.md`) con la ficha de levantamiento

| Ficha | Sección del perfil |
| --- | --- |
| Nombre, descripción, trato y tono | Título, primera frase y línea de trato |
| Dirección y teléfono | Datos generales |
| Horario y festivos | Horario |
| Servicios y precios | Servicios |
| Productos, descripciones y precios | Productos y precios |
| Zonas, costos, tiempos y pedido mínimo | Domicilios |
| Formas de pago | Medios de pago |
| Lo prohibido y las urgencias del rubro | Reglas de seguridad |
| Citas (si aplica) | Citas |
| Preguntas que más le hacen | Preguntas frecuentes |
| Mensaje al pasar a una persona | Mensaje de derivación |

Reglas que el motor necesita:

- Conserve **exactamente** el título `## Mensaje de derivación`: el motor lo busca por ese título (si falta, usa un mensaje genérico).
- Las secciones "Saludo", "Cómo iniciar un pedido" y "Medios de pago" traen instrucciones para el asistente que coinciden con cómo funciona el motor: no las cambie, solo bórrelas si el negocio no usa esa función.
- En una urgencia el asistente no debe derivar (el cliente perdería el teléfono que se le da).
- Si hay citas: el asistente toma los datos y deriva; el dueño recibe el aviso de derivación con el teléfono del cliente y el resumen "Solicitud de cita: …" (sub-fases 6a/6b).

## 4. Llenar los recursos (`recursos_<clave>.json`)

JSON no admite comentarios: las indicaciones van aquí. El motor valida todo al arrancar y **no arranca** si algo está mal (mejor un error claro que un fallo con un cliente real).

| Sección | Qué poner | Límites que valida el motor |
| --- | --- | --- |
| `ubicacion` | Latitud y longitud reales del negocio (Google Maps → clic derecho sobre el punto → copiar coordenadas), nombre y dirección. Si no se quiere mapa, borre `ubicacion` y `enlaces` completos. | Latitud −90 a 90, longitud −180 a 180; nombre y dirección no vacíos. |
| `enlaces.mapa` | `url` con las mismas coordenadas: `https://www.google.com/maps?q=LAT,LON`. La clave debe llamarse `mapa` para que se envíe junto a la ubicación. | URL `https://`; `texto_boton` de 1 a 20 caracteres. |
| `imagenes.qr_ejemplo` | El archivo del QR, en la misma carpeta del cliente. | Debe existir; JPG o PNG; máximo 5 MB. |
| `catalogo` | Los productos que se pueden pedir por el bot. La clave de cada uno (por ejemplo `pan_rollo`) es interna: minúsculas, sin espacios. | Máximo 10 productos; `nombre` de 1 a 24 caracteres; `precio` entero en pesos, sin puntos ni decimales; `unidad` no vacía. |
| `botones.bienvenida` | Hasta 3 opciones. `equivale_a` es la frase que el asistente recibe cuando el cliente toca el botón. El id `hacer_pedido` es especial: inicia el pedido guiado (solo si hay `catalogo`). | Máximo 3 botones; `titulo` de 1 a 20 caracteres; ids únicos. |
| `domicilio` | `pedido_minimo` (entero, puede ser 0) y una entrada por zona con `nombre`, `costo` (entero) y `tiempo_estimado`. | Nombre de zona de 1 a 24 caracteres; costos enteros ≥ 0. |

### Agenda de citas (opcional)

Si el negocio agenda citas por el bot, agregue la sección `citas` en la raíz del JSON (y deje el bloque "Con agenda" en el perfil). Ejemplo:

```json
"citas": {
  "duracion_minutos": 30,
  "cupos_por_horario": 1,
  "anticipacion_minima_minutos": 60,
  "dias_hacia_adelante": 14,
  "max_citas_por_cliente": 3,
  "retencion_dias": 30,
  "festivos": "cerrado",
  "dias_bloqueados": ["2026-12-24"],
  "telefono_negocio": "300 000 0000",
  "horario": {
    "lunes": [["08:00", "12:00"], ["14:00", "18:00"]],
    "sabado": [["09:00", "13:00"]]
  },
  "datos": [
    {"clave": "nombre", "pregunta": "¿A nombre de quién agendamos la cita?", "etiqueta": "Nombre"},
    {"clave": "motivo", "pregunta": "¿Cuál es el motivo de la cita?", "etiqueta": "Motivo"}
  ]
}
```

| Campo | Qué es | Límites |
| --- | --- | --- |
| `duracion_minutos` (obligatorio) | Duración de cada cita; las horas se ofrecen cada tantos minutos. | 5 a 480. |
| `horario` (obligatorio) | Franjas por día: `lunes` … `domingo` (minúsculas, sin tilde). Día ausente = no se atiende. | `"HH:MM"` 24 h; inicio < fin; franjas sin cruzarse. |
| `datos` (obligatorio) | Lo que se le pregunta al cliente, uno por mensaje, después de que autoriza el tratamiento de datos. | 1 a 5; `clave` en minúsculas; `etiqueta` hasta 20 caracteres. |
| `cupos_por_horario` | Cuántas citas a la misma hora (p. ej. 2 profesionales). | 1 a 20; por defecto 1. |
| `anticipacion_minima_minutos` | Cuánto antes se puede reservar. | Por defecto 60. |
| `dias_hacia_adelante` | Hasta cuántos días después de hoy se ofrece. | 1 a 60; por defecto 14. |
| `max_citas_por_cliente` | Citas futuras por número, para que nadie llene la agenda. | 1 a 20; por defecto 3. |
| `retencion_dias` | Días después de la cita en que se borran los datos personales. | 1 a 365; por defecto 30. |
| `recordatorio_horas` | Cuántas horas antes de la cita se le recuerda al cliente. `0` = sin recordatorios. | 0 a 168; por defecto 24. |
| `festivos` | `"cerrado"` o `"abierto"` (usa el horario del día). | Por defecto `"cerrado"`. |
| `dias_bloqueados` | Vacaciones o cierres puntuales. | Fechas `"AAAA-MM-DD"`. |
| `telefono_negocio` | Se le da al cliente si no autoriza el tratamiento de datos. | Opcional. |

Un botón de bienvenida con id `agendar_cita` abre la agenda directamente. Cambiar la configuración no toca las citas ya agendadas: solo cambia lo que se ofrece desde ese momento. Para el aviso de cita nueva al dueño, ver `docs/plantilla_aviso_cita.md`; para el recordatorio al cliente (variables `PLANTILLA_RECORDATORIO_CITA_NOMBRE` / `_IDIOMA` en el `.env`), ver `docs/plantilla_recordatorio_cita.md`.

Si el negocio no toma pedidos por el bot, borre `catalogo`, `domicilio` y el botón `hacer_pedido`. Solo se admiten estas secciones en la raíz: `ubicacion`, `enlaces`, `imagenes`, `catalogo`, `domicilio`, `botones`, `citas`.

## 5. Revisar que no quedó nada de la plantilla y validar en el PC

PowerShell en modo normal, en `C:\Users\Camilo\BotWhatsApp`:

```powershell
Select-String -Path "clientes\$clave\*.md", "clientes\$clave\*.json" -Pattern '\[[A-ZÁÉÍÓÚÑ0-9 ]+', 'EJEMPLO' -CaseSensitive
./venv/Scripts/python.exe -c "import perfiles_negocio as p, recursos as r, webhook as w; c='$clave'; r.cargar_recursos(p.ruta_recursos_para_clave(c)); print('Perfil OK. Mensaje de derivacion:', w._extraer_mensaje_derivacion(p.ruta_perfil_para_clave(c)))"
```

- La primera línea no debe mostrar nada (si muestra algo, quedó un campo de la plantilla sin llenar; el aviso del QR de ejemplo es la excepción si es una demo).
- La segunda debe terminar en `Perfil OK.`; si no, el mensaje de error dice qué campo corregir.

## 6. Subir el perfil al droplet (PC, PowerShell en modo normal)

```powershell
scp -r "clientes\$clave" droplet-bot:/home/camilo/BotWhatsApp/clientes/
```

El contenedor ve la carpeta al instante (`./clientes` está montada de solo lectura), pero el bot no cambia de perfil hasta el paso 7.

## 7. Activar el perfil en el droplet

Entrar con `ssh droplet-bot` y, **dentro del droplet** (cambie `mi_cliente` por la clave):

```bash
cd /home/camilo/BotWhatsApp && cp -p .env .env.bak-$(date +%Y%m%d) && sed -i 's/^PERFIL_NEGOCIO=.*/PERFIL_NEGOCIO=mi_cliente/' .env && grep -c '^PERFIL_NEGOCIO=mi_cliente$' .env
```

- Saca una copia del `.env` con los mismos permisos, cambia solo esa línea e imprime solo un número, nunca el contenido: `1` = quedó bien; `0` = la línea `PERFIL_NEGOCIO=` no existía y no cambió nada.

Recrear el contenedor (`docker compose restart` **no** vuelve a leer el `.env`):

```bash
docker compose up -d --force-recreate && docker compose ps
```

- Debe quedar `healthy`. Si el perfil tiene un error, el contenedor se reinicia en bucle: revise con `docker compose logs --tail 30 bot-whatsapp` (solo las últimas líneas) y corrija en el PC (pasos 4-6).
- Volver al perfil anterior: `cp -p .env.bak-AAAAMMDD .env` (con la fecha de la copia) y el mismo `docker compose up -d --force-recreate`.

## 8. Probar en vivo

Desde un celular que no sea el `NUMERO_DUENO`: saludo (botones), una pregunta frecuente, la ubicación, un pedido completo si aplica, y una derivación (escribir "quiero hablar con una persona") para confirmar que el aviso le llega al dueño. Recuerde: como máximo un aviso de derivación por cliente cada 30 minutos.
