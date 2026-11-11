import logging
import time
import unicodedata

from pago_pedido import PREFIJO_BOTON_PAGO_NO_LLEGO, PREFIJO_BOTON_PAGO_RECIBIDO
from pedidos import ESTADO_EN_CONSTRUCCION, ESTADO_PAGO_PENDIENTE, ESTADO_PAGO_POR_VERIFICAR, Pedidos
from telefono import enmascarar_numero

logger = logging.getLogger(__name__)

SEGUNDOS_TIMEOUT_PEDIDO = 30 * 60
CANTIDAD_MINIMA = 1
CANTIDAD_MAXIMA = 50

ID_BOTON_HACER_PEDIDO = "hacer_pedido"
ID_BOTON_AGREGAR_OTRO = "agregar_otro"
ID_BOTON_CONTINUAR = "continuar"
ID_BOTON_ACEPTO = "acepto_datos"
ID_BOTON_NO_ACEPTO = "no_acepto_datos"
ID_BOTON_DOMICILIO = "domicilio"
ID_BOTON_RECOGER_LOCAL = "recoger_local"
ID_BOTON_CONFIRMAR = "confirmar"
ID_BOTON_CAMBIAR = "cambiar"
ID_BOTON_CANCELAR = "cancelar"
ID_BOTON_SEGUIR = "seguir_pedido"
ID_BOTON_PAGO_QR = "pago_qr"
ID_BOTON_PAGO_EFECTIVO = "pago_efectivo"

PALABRAS_CLAVE_CANCELAR = {"cancelar", "cancela", "salir"}
PALABRAS_CLAVE_PERSONA = {"persona", "asesor", "humano", "humana", "hablar con alguien"}

ESTADOS_PAGO = {ESTADO_PAGO_PENDIENTE, ESTADO_PAGO_POR_VERIFICAR}

MENSAJE_CANCELADO_POR_CLIENTE = "Su pedido en construcción fue cancelado. Escríbame cuando quiera empezar de nuevo."
MENSAJE_CANCELADO_POR_INACTIVIDAD = (
    "Como pasaron más de 30 minutos sin respuesta, cancelé el pedido en construcción. "
    "Escríbame cuando quiera empezar de nuevo."
)
MENSAJE_ENTRADA_NO_RECONOCIDA = (
    "No entendí esa respuesta. Para seguir con su pedido, elija una de las opciones. "
    "Si desea cancelar, escriba *cancelar*."
)
MENSAJE_CANCELAR_NO_DISPONIBLE_EN_VERIFICACION = (
    "Como ya recibimos su comprobante, no podemos cancelar el pedido automáticamente. "
)
MENSAJE_COMPROBANTE_RECIBIDO = (
    "Recibimos su comprobante. Estamos verificando el pago y le confirmamos en breve."
)
MENSAJE_PAGO_EN_VERIFICACION = (
    "Ya estamos verificando su pago, le confirmamos en breve. No es necesario enviar nada más."
)
MENSAJE_DOCUMENTO_EN_PAGO_PENDIENTE = (
    "Recibí un archivo, pero necesito una foto o captura de pantalla del comprobante, no un "
    "documento. ¿Puede enviarla como imagen?"
)
TEXTO_CONSENTIMIENTO = (
    "Para tomar su pedido necesito guardar la dirección de entrega. Estos datos se usan solo "
    "para este pedido, conforme a la Ley 1581 de 2012, y puede pedir que se eliminen cuando "
    "quiera. ¿Está de acuerdo?"
)
TEXTO_CONSENTIMIENTO_RECHAZADO = (
    "Entendido, sin su dirección no podemos llevarle el pedido. ¿Prefiere recogerlo en el local?"
)
TEXTO_PEDIR_DIRECCION = "Por favor compárteme su dirección exacta (puede escribirla o compartir su ubicación)."


def _formatear_pesos(valor: int) -> str:
    return f"${valor:,}".replace(",", ".")


def _normalizar(texto: str) -> str:
    # Minúsculas y sin tildes/diacríticos, para reconocer "Cancelar", "CANCELAR"
    # o "cancélar" igual que "cancelar" — sin ninguna interpretación con IA, solo
    # comparación exacta contra una lista corta de frases (ver PALABRAS_CLAVE_*).
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower()


def _texto_entrante(mensaje: dict) -> str | None:
    if mensaje.get("type") == "text":
        return mensaje.get("text", {}).get("body")
    return None


def _tipo_e_id_interactivo(mensaje: dict) -> tuple[str | None, str | None]:
    if mensaje.get("type") != "interactive":
        return None, None
    interactivo = mensaje.get("interactive", {})
    tipo = interactivo.get("type")
    if tipo == "button_reply":
        return tipo, interactivo.get("button_reply", {}).get("id")
    if tipo == "list_reply":
        return tipo, interactivo.get("list_reply", {}).get("id")
    return tipo, None


def _parsear_cantidad(texto: str) -> int | None:
    texto = texto.strip()
    if not texto.isdigit():
        return None
    cantidad = int(texto)
    if not (CANTIDAD_MINIMA <= cantidad <= CANTIDAD_MAXIMA):
        return None
    return cantidad


def _construir_resumen(pedido: dict, domicilio: dict) -> tuple[str, int]:
    lineas = ["Resumen de su pedido:"]
    total = 0
    for item in pedido["items"]:
        lineas.append(f'- {item["cantidad"]} x {item["nombre"]}: {_formatear_pesos(item["subtotal"])}')
        total += item["subtotal"]

    tipo_entrega = pedido["tipo_entrega"]
    zona_domicilio = pedido["zona_domicilio"]
    if tipo_entrega == "domicilio" and zona_domicilio is not None:
        nombre_zona = domicilio[zona_domicilio]["nombre"]
        costo_domicilio = domicilio[zona_domicilio]["costo"]
        lineas.append(f"Entrega: Domicilio - {nombre_zona}")
        if pedido.get("direccion_texto"):
            lineas.append(f"Dirección: {pedido['direccion_texto']}")
        elif pedido.get("latitud") is not None:
            lineas.append("Dirección: ubicación compartida por WhatsApp")
        lineas.append(f"Costo de domicilio: {_formatear_pesos(costo_domicilio)}")
        total += costo_domicilio
    else:
        lineas.append("Entrega: Recoger en el local.")

    lineas.append(f"Total: {_formatear_pesos(total)}")
    return "\n".join(lineas), total


class FlujoPedido:
    def __init__(
        self,
        pedidos: Pedidos,
        catalogo: dict,
        domicilio: dict,
        mensaje_derivacion: str,
        enviar_texto_fn,
        enviar_botones_fn,
        enviar_lista_fn,
        reloj=time.time,
        numero_dueno: str | None = None,
        enviar_imagen_fn=None,
        obtener_media_id_fn=None,
        reenviar_media_fn=None,
        imagen_qr: dict | None = None,
        enviar_plantilla_fn=None,
        enviar_imagen_con_wamid_fn=None,
        plantilla_aviso_dueno_nombre: str | None = None,
        plantilla_aviso_dueno_idioma: str | None = None,
    ) -> None:
        self._pedidos = pedidos
        self._catalogo = catalogo
        self._domicilio = domicilio
        self._mensaje_derivacion = mensaje_derivacion
        self._enviar_texto_fn = enviar_texto_fn
        self._enviar_botones_fn = enviar_botones_fn
        self._enviar_lista_fn = enviar_lista_fn
        self._reloj = reloj
        self._numero_dueno = numero_dueno
        self._enviar_imagen_fn = enviar_imagen_fn
        self._obtener_media_id_fn = obtener_media_id_fn
        self._reenviar_media_fn = reenviar_media_fn
        self._imagen_qr = imagen_qr
        self._enviar_plantilla_fn = enviar_plantilla_fn
        self._enviar_imagen_con_wamid_fn = enviar_imagen_con_wamid_fn
        self._plantilla_aviso_dueno_nombre = plantilla_aviso_dueno_nombre
        self._plantilla_aviso_dueno_idioma = plantilla_aviso_dueno_idioma
        self._manejadores = {
            "producto": self._manejar_producto,
            "cantidad": self._manejar_cantidad,
            "agregar_otro_o_continuar": self._manejar_agregar_otro_o_continuar,
            "entrega": self._manejar_entrega,
            "minimo_no_alcanzado": self._manejar_minimo_no_alcanzado,
            "consentimiento": self._manejar_consentimiento,
            "consentimiento_rechazado": self._manejar_consentimiento_rechazado,
            "zona": self._manejar_zona,
            "direccion": self._manejar_direccion,
            "confirmacion": self._manejar_confirmacion,
            "metodo_pago": self._manejar_metodo_pago,
            "pago_pendiente": self._manejar_pago_pendiente,
            "pago_por_verificar": self._manejar_pago_por_verificar,
        }

    # -- Envío de mensajes (adaptadores delgados sobre las funciones inyectadas) --

    def _enviar_texto(self, numero: str, texto: str) -> bool:
        return self._enviar_texto_fn(numero, texto)

    def _enviar_botones(self, numero: str, texto_cuerpo: str, botones: list[tuple[str, str]]) -> bool:
        return self._enviar_botones_fn(
            numero, texto_cuerpo, [{"id": id_, "titulo": titulo} for id_, titulo in botones]
        )

    def _enviar_lista(self, numero: str, texto_cuerpo: str, texto_boton: str, secciones: list[dict]) -> bool:
        return self._enviar_lista_fn(numero, texto_cuerpo, texto_boton, secciones)

    def _enviar_menu(self, numero: str, texto_cuerpo: str) -> None:
        filas = [
            {"id": clave, "titulo": producto["nombre"], "descripcion": _formatear_pesos(producto["precio"])}
            for clave, producto in self._catalogo.items()
        ]
        self._enviar_lista(numero, texto_cuerpo, "Ver menú", [{"titulo": "Menú", "filas": filas}])

    def _enviar_lista_zonas(self, numero: str) -> None:
        filas = [
            {
                "id": clave,
                "titulo": zona.get("nombre", clave),
                "descripcion": f'{_formatear_pesos(zona["costo"])} · {zona["tiempo_estimado"]}',
            }
            for clave, zona in self._domicilio.items()
            if clave != "pedido_minimo"
        ]
        self._enviar_lista(
            numero, "Elija la zona de su domicilio:", "Ver zonas", [{"titulo": "Zonas de domicilio", "filas": filas}]
        )

    def _enviar_resumen_y_confirmacion(self, numero: str, pedido: dict) -> None:
        texto_resumen, _ = _construir_resumen(pedido, self._domicilio)
        self._enviar_botones(
            numero,
            f"{texto_resumen}\n\n¿Confirma su pedido?",
            [(ID_BOTON_CONFIRMAR, "Confirmar"), (ID_BOTON_CAMBIAR, "Cambiar"), (ID_BOTON_CANCELAR, "Cancelar")],
        )

    def _pedir_consentimiento(self, numero: str) -> None:
        self._enviar_botones(numero, TEXTO_CONSENTIMIENTO, [(ID_BOTON_ACEPTO, "Acepto"), (ID_BOTON_NO_ACEPTO, "No acepto")])

    def _pedir_tipo_entrega(self, numero: str) -> None:
        self._enviar_botones(
            numero,
            "¿Cómo desea recibir su pedido?",
            [(ID_BOTON_DOMICILIO, "Domicilio"), (ID_BOTON_RECOGER_LOCAL, "Recoger en el local")],
        )

    def _avisar_minimo_no_alcanzado(self, numero: str, pedido: dict) -> None:
        subtotal = sum(item["subtotal"] for item in pedido["items"])
        pedido_minimo = self._domicilio.get("pedido_minimo")
        self._enviar_botones(
            numero,
            (
                f"Para domicilio el pedido mínimo es {_formatear_pesos(pedido_minimo)} y su pedido suma "
                f"{_formatear_pesos(subtotal)}. Puede agregar algo más o recoger en el local."
            ),
            [(ID_BOTON_AGREGAR_OTRO, "Agregar otro"), (ID_BOTON_RECOGER_LOCAL, "Recoger en el local")],
        )

    def _pedir_agregar_otro_o_continuar(self, numero: str) -> None:
        self._enviar_botones(
            numero,
            "¿Desea agregar algo más a su pedido?",
            [(ID_BOTON_AGREGAR_OTRO, "Agregar otro"), (ID_BOTON_CONTINUAR, "Continuar")],
        )

    def _pedir_recoger_tras_rechazo(self, numero: str) -> None:
        self._enviar_botones(
            numero,
            TEXTO_CONSENTIMIENTO_RECHAZADO,
            [(ID_BOTON_RECOGER_LOCAL, "Recoger en el local"), (ID_BOTON_CANCELAR, "Cancelar")],
        )

    def _pedir_metodo_pago(self, numero: str) -> None:
        self._enviar_botones(
            numero,
            "¿Cómo desea pagar?",
            [(ID_BOTON_PAGO_QR, "QR / transferencia"), (ID_BOTON_PAGO_EFECTIVO, "Efectivo")],
        )

    def _pedir_comprobante(self, numero: str, pedido_id: int, total: int) -> None:
        texto_valor = f"Valor a pagar: {_formatear_pesos(total)} · Referencia: Pedido #{pedido_id}"
        media_id = None
        if self._imagen_qr is not None and self._obtener_media_id_fn is not None:
            media_id = self._obtener_media_id_fn(self._imagen_qr["clave"], self._imagen_qr["archivo"])
        if media_id is not None and self._enviar_imagen_fn is not None:
            self._enviar_imagen_fn(numero, media_id, caption=texto_valor)
        else:
            if self._imagen_qr is not None:
                logger.warning(
                    "No se pudo obtener el media id del QR de ejemplo; se envía solo el texto de pago."
                )
            self._enviar_texto(numero, texto_valor)
        self._enviar_botones(
            numero,
            "Cuando pague, envíe aquí la foto del comprobante. Si prefiere, también puede pagar en efectivo.",
            [(ID_BOTON_PAGO_EFECTIVO, "Pagar en efectivo")],
        )

    def _confirmar_pago_efectivo(self, numero: str, pedido: dict, ahora: float) -> None:
        texto_resumen, total = _construir_resumen(pedido, self._domicilio)
        self._pedidos.confirmar_efectivo(pedido["id"], total, ahora)
        logger.info(
            "Pedido #%s confirmado con pago en efectivo (remitente=%s)",
            pedido["id"], enmascarar_numero(numero),
        )
        if pedido["tipo_entrega"] == "domicilio":
            linea_tiempo = f'Tiempo estimado: {self._domicilio[pedido["zona_domicilio"]]["tiempo_estimado"]}.'
            linea_pago = "Pago: en efectivo al recibir su pedido."
        else:
            linea_tiempo = "Puede recoger su pedido en el local."
            linea_pago = "Pago: en efectivo al recoger su pedido."
        self._enviar_texto(
            numero, f'Pedido #{pedido["id"]} recibido.\n\n{texto_resumen}\n{linea_tiempo}\n{linea_pago}'
        )

    def _avisar_dueno(self, pedido: dict, mensaje: dict) -> None:
        if not self._numero_dueno:
            return

        media_id_entrante = mensaje.get("image", {}).get("id")
        media_id_reenviado = None
        if media_id_entrante and self._reenviar_media_fn is not None:
            media_id_reenviado = self._reenviar_media_fn(media_id_entrante)

        if self._plantilla_aviso_dueno_nombre and self._plantilla_aviso_dueno_idioma and self._enviar_plantilla_fn is not None:
            self._avisar_dueno_con_plantilla(pedido, media_id_reenviado)
            return

        texto_resumen, _ = _construir_resumen(pedido, self._domicilio)
        texto_aviso = (
            f'Pedido #{pedido["id"]} · Cliente {enmascarar_numero(pedido["numero_cliente"])}\n'
            f"{texto_resumen}\n\n"
            f"Antes de confirmar, verifique en su app de Bold o Nequi que llegaron "
            f'{_formatear_pesos(pedido["total"])} con referencia Pedido #{pedido["id"]}.'
        )

        if media_id_reenviado is not None and self._enviar_imagen_fn is not None:
            envio_ok = self._enviar_imagen_fn(self._numero_dueno, media_id_reenviado, caption=texto_aviso)
        else:
            envio_ok = self._enviar_texto(self._numero_dueno, texto_aviso)

        botones_ok = self._enviar_botones(
            self._numero_dueno,
            "¿Qué desea hacer?",
            [
                (f"{PREFIJO_BOTON_PAGO_RECIBIDO}{pedido['id']}", "Pago recibido"),
                (f"{PREFIJO_BOTON_PAGO_NO_LLEGO}{pedido['id']}", "No ha llegado"),
            ],
        )

        if not (envio_ok and botones_ok):
            logger.warning(
                "No se pudo completar el aviso al dueño del pedido #%s (posible ventana de 24 "
                "horas de WhatsApp sin mensaje previo del dueño, o fallo de red). El pedido queda "
                "en pago_por_verificar; se puede confirmar con gestionar_pedido.py.",
                pedido["id"],
            )

    def _avisar_dueno_con_plantilla(self, pedido: dict, media_id_reenviado: str | None) -> None:
        # Siempre por plantilla (ver docs/plantilla_aviso_dueno.md): es el único
        # canal garantizado fuera de la ventana de 24 horas. El comprobante, si
        # se pudo reenviar, se intenta mostrar APARTE como mejor esfuerzo — su
        # fallo no afecta el aviso principal, que ya quedó garantizado.
        ahora = self._reloj()
        ok, wamid = self._enviar_plantilla_fn(
            self._numero_dueno,
            self._plantilla_aviso_dueno_nombre,
            self._plantilla_aviso_dueno_idioma,
            [str(pedido["id"]), _formatear_pesos(pedido["total"])],
            f"{PREFIJO_BOTON_PAGO_RECIBIDO}{pedido['id']}",
            f"{PREFIJO_BOTON_PAGO_NO_LLEGO}{pedido['id']}",
        )
        if ok and wamid:
            self._pedidos.registrar_wamid_aviso_dueno(wamid, pedido["id"], "plantilla", ahora)
        if not ok:
            logger.warning(
                "No se pudo enviar la plantilla de aviso al dueño del pedido #%s.", pedido["id"]
            )

        if media_id_reenviado is not None and self._enviar_imagen_con_wamid_fn is not None:
            ok_comprobante, wamid_comprobante = self._enviar_imagen_con_wamid_fn(
                self._numero_dueno, media_id_reenviado, caption=f'Comprobante del pedido #{pedido["id"]}'
            )
            if ok_comprobante and wamid_comprobante:
                self._pedidos.registrar_wamid_aviso_dueno(
                    wamid_comprobante, pedido["id"], "comprobante", ahora
                )

    def _derivar_sin_cancelar(self, numero: str, pedido: dict, ahora: float, texto: str) -> None:
        self._pedidos.tocar(pedido["id"], ahora)
        logger.info(
            "Pedido #%s derivado a una persona sin cancelar (estado=%s, remitente=%s)",
            pedido["id"], pedido["estado"], enmascarar_numero(numero),
        )
        self._enviar_texto(numero, texto)

    def _reenviar_paso_actual(self, numero: str, pedido: dict) -> None:
        # Reenvía el MISMO interactivo del paso en el que está el pedido (los
        # mismos botones, la misma lista o el mismo resumen), para que el
        # cliente pueda seguir sin perder lo ya elegido. Nunca agrega botones
        # de más: cada paso ya respeta el límite de 3 de WhatsApp.
        paso = pedido["paso"]
        if paso == "producto":
            self._enviar_menu(numero, "Elija un producto del menú:")
        elif paso == "agregar_otro_o_continuar":
            self._pedir_agregar_otro_o_continuar(numero)
        elif paso == "consentimiento":
            self._pedir_consentimiento(numero)
        elif paso == "consentimiento_rechazado":
            self._pedir_recoger_tras_rechazo(numero)
        elif paso == "entrega":
            self._pedir_tipo_entrega(numero)
        elif paso == "minimo_no_alcanzado":
            self._avisar_minimo_no_alcanzado(numero, pedido)
        elif paso == "zona":
            self._enviar_lista_zonas(numero)
        elif paso == "confirmacion":
            self._enviar_resumen_y_confirmacion(numero, pedido)
        elif paso == "metodo_pago":
            self._pedir_metodo_pago(numero)
        elif paso == "pago_pendiente":
            self._pedir_comprobante(numero, pedido["id"], pedido["total"])
        # paso == "direccion" no reenvía nada aquí: espera texto libre o una
        # ubicación compartida, no un interactivo con botones fijos. paso ==
        # "pago_por_verificar" tampoco: su manejador nunca devuelve False (ver
        # _manejar_pago_por_verificar), así que nunca llega hasta aquí.

    # -- Entradas públicas --

    def iniciar(self, numero: str, perfil: str, mensaje: dict) -> None:
        self._pedidos.crear_en_construccion(numero, perfil, self._reloj())
        self.manejar_mensaje(numero, mensaje)

    def manejar_mensaje(self, numero: str, mensaje: dict) -> None:
        pedido = self._pedidos.obtener_activo(numero)
        if pedido is None:
            return

        ahora = self._reloj()

        if pedido["estado"] == ESTADO_EN_CONSTRUCCION and ahora - pedido["actualizado_en"] > SEGUNDOS_TIMEOUT_PEDIDO:
            self._pedidos.cancelar(pedido["id"], ahora)
            logger.info(
                "Pedido #%s cancelado por inactividad de 30 minutos (remitente=%s)",
                pedido["id"], enmascarar_numero(numero),
            )
            self._enviar_texto(numero, MENSAJE_CANCELADO_POR_INACTIVIDAD)
            return

        texto = _texto_entrante(mensaje)
        _, id_interactivo = _tipo_e_id_interactivo(mensaje)
        texto_normalizado = _normalizar(texto) if texto is not None else None

        if texto_normalizado is not None and texto_normalizado in PALABRAS_CLAVE_CANCELAR:
            if pedido["estado"] == ESTADO_PAGO_POR_VERIFICAR:
                self._derivar_sin_cancelar(
                    numero, pedido, ahora,
                    MENSAJE_CANCELAR_NO_DISPONIBLE_EN_VERIFICACION + self._mensaje_derivacion,
                )
            else:
                self._pedidos.cancelar(pedido["id"], ahora)
                logger.info(
                    "Pedido #%s cancelado por el cliente (remitente=%s)", pedido["id"], enmascarar_numero(numero)
                )
                self._enviar_texto(numero, MENSAJE_CANCELADO_POR_CLIENTE)
            return

        if texto_normalizado is not None and texto_normalizado in PALABRAS_CLAVE_PERSONA:
            if pedido["estado"] in ESTADOS_PAGO:
                self._derivar_sin_cancelar(numero, pedido, ahora, self._mensaje_derivacion)
            else:
                self._pedidos.cancelar(pedido["id"], ahora)
                logger.info(
                    "Pedido #%s cancelado y derivado a una persona (remitente=%s)",
                    pedido["id"], enmascarar_numero(numero),
                )
                self._enviar_texto(numero, self._mensaje_derivacion)
            return

        if id_interactivo == ID_BOTON_CANCELAR:
            if pedido["estado"] == ESTADO_PAGO_POR_VERIFICAR:
                self._derivar_sin_cancelar(
                    numero, pedido, ahora,
                    MENSAJE_CANCELAR_NO_DISPONIBLE_EN_VERIFICACION + self._mensaje_derivacion,
                )
            else:
                self._pedidos.cancelar(pedido["id"], ahora)
                logger.info(
                    "Pedido #%s cancelado por el cliente (remitente=%s)", pedido["id"], enmascarar_numero(numero)
                )
                self._enviar_texto(numero, MENSAJE_CANCELADO_POR_CLIENTE)
            return

        if id_interactivo == ID_BOTON_SEGUIR:
            # Ya no se ofrece este botón (se reemplazó por el reenvío del propio
            # paso actual, más abajo), pero se sigue reconociendo por si queda
            # visible en una conversación vieja: no debe cancelar ni romper nada.
            self._pedidos.tocar(pedido["id"], ahora)
            self._enviar_texto(numero, "Claro, continuemos con su pedido.")
            return

        manejador = self._manejadores[pedido["paso"]]
        reconocido = manejador(numero, pedido, mensaje, ahora)
        if not reconocido:
            self._pedidos.tocar(pedido["id"], ahora)
            logger.info(
                "Entrada no reconocida en el paso '%s' del pedido #%s (remitente=%s)",
                pedido["paso"], pedido["id"], enmascarar_numero(numero),
            )
            self._enviar_texto(numero, MENSAJE_ENTRADA_NO_RECONOCIDA)
            self._reenviar_paso_actual(numero, pedido)

    # -- Manejadores por paso: cada uno recibe (numero, pedido, mensaje, ahora) y
    #    devuelve True si reconoció y procesó la entrada, False si no aplica (lo
    #    que dispara el mensaje genérico de "entrada no reconocida"). --

    def _manejar_producto(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo == "button_reply" and id_interactivo == ID_BOTON_HACER_PEDIDO:
            self._pedidos.tocar(pedido["id"], ahora)
            self._enviar_menu(numero, "Elija un producto del menú:")
            return True
        if tipo_interactivo == "list_reply":
            producto = self._catalogo.get(id_interactivo)
            if producto is None:
                return False
            self._pedidos.fijar_producto_pendiente(pedido["id"], id_interactivo, ahora)
            self._enviar_texto(numero, f'¿Cuántas unidades de "{producto["nombre"]}" desea (1 a 50)?')
            return True
        return False

    def _manejar_cantidad(self, numero, pedido, mensaje, ahora) -> bool:
        texto = _texto_entrante(mensaje)
        if texto is None:
            return False

        producto = self._catalogo.get(pedido["producto_pendiente"])
        cantidad = _parsear_cantidad(texto)
        if cantidad is None:
            self._pedidos.tocar(pedido["id"], ahora)
            nombre = producto["nombre"] if producto else "ese producto"
            self._enviar_texto(
                numero,
                f'Escriba solo el número de unidades, por ejemplo: 3 (entre 1 y 50), para "{nombre}".',
            )
            return True

        self._pedidos.agregar_item(
            pedido["id"], pedido["producto_pendiente"], producto["nombre"], producto["precio"], cantidad, ahora
        )
        self._enviar_botones(
            numero,
            f'Agregado: {cantidad} x "{producto["nombre"]}". ¿Desea agregar algo más?',
            [(ID_BOTON_AGREGAR_OTRO, "Agregar otro"), (ID_BOTON_CONTINUAR, "Continuar")],
        )
        return True

    def _manejar_agregar_otro_o_continuar(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "button_reply":
            return False

        if id_interactivo == ID_BOTON_AGREGAR_OTRO:
            self._pedidos.fijar_paso(pedido["id"], "producto", ahora)
            self._enviar_menu(numero, "Elija otro producto del menú:")
            return True

        if id_interactivo == ID_BOTON_CONTINUAR:
            self._pedidos.fijar_paso(pedido["id"], "entrega", ahora)
            self._pedir_tipo_entrega(numero)
            return True
        return False

    def _manejar_consentimiento(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "button_reply":
            return False

        if id_interactivo == ID_BOTON_ACEPTO:
            self._pedidos.fijar_consentimiento(pedido["id"], True, ahora, paso_siguiente="zona")
            self._enviar_lista_zonas(numero)
            return True
        if id_interactivo == ID_BOTON_NO_ACEPTO:
            self._pedidos.fijar_consentimiento(pedido["id"], False, ahora, paso_siguiente="consentimiento_rechazado")
            logger.info(
                "Pedido #%s: consentimiento de datos rechazado, se ofrece recoger en el local (remitente=%s)",
                pedido["id"], enmascarar_numero(numero),
            )
            self._pedir_recoger_tras_rechazo(numero)
            return True
        return False

    def _manejar_consentimiento_rechazado(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "button_reply":
            return False

        if id_interactivo == ID_BOTON_RECOGER_LOCAL:
            self._pedidos.fijar_entrega(pedido["id"], "recoger", ahora, paso_siguiente="confirmacion")
            self._enviar_resumen_y_confirmacion(numero, self._pedidos.obtener_en_construccion(numero))
            return True
        return False

    def _manejar_entrega(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "button_reply":
            return False

        if id_interactivo == ID_BOTON_RECOGER_LOCAL:
            self._pedidos.fijar_entrega(pedido["id"], "recoger", ahora, paso_siguiente="confirmacion")
            self._enviar_resumen_y_confirmacion(numero, self._pedidos.obtener_en_construccion(numero))
            return True

        if id_interactivo == ID_BOTON_DOMICILIO:
            subtotal = sum(item["subtotal"] for item in pedido["items"])
            pedido_minimo = self._domicilio.get("pedido_minimo")
            if pedido_minimo is not None and subtotal < pedido_minimo:
                self._pedidos.fijar_paso(pedido["id"], "minimo_no_alcanzado", ahora)
                self._avisar_minimo_no_alcanzado(numero, pedido)
            else:
                self._pedidos.fijar_paso(pedido["id"], "consentimiento", ahora)
                self._pedir_consentimiento(numero)
            return True
        return False

    def _manejar_minimo_no_alcanzado(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "button_reply":
            return False

        if id_interactivo == ID_BOTON_AGREGAR_OTRO:
            self._pedidos.fijar_paso(pedido["id"], "producto", ahora)
            self._enviar_menu(numero, "Elija otro producto del menú:")
            return True
        if id_interactivo == ID_BOTON_RECOGER_LOCAL:
            self._pedidos.fijar_entrega(pedido["id"], "recoger", ahora, paso_siguiente="confirmacion")
            self._enviar_resumen_y_confirmacion(numero, self._pedidos.obtener_en_construccion(numero))
            return True
        return False

    def _manejar_zona(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "list_reply":
            return False
        if id_interactivo == "pedido_minimo" or id_interactivo not in self._domicilio:
            return False

        self._pedidos.fijar_entrega(
            pedido["id"], "domicilio", ahora, paso_siguiente="direccion", zona_domicilio=id_interactivo
        )
        self._enviar_texto(numero, TEXTO_PEDIR_DIRECCION)
        return True

    def _manejar_direccion(self, numero, pedido, mensaje, ahora) -> bool:
        if mensaje.get("type") == "location":
            ubicacion = mensaje.get("location", {})
            try:
                latitud = float(ubicacion["latitude"])
                longitud = float(ubicacion["longitude"])
            except (KeyError, TypeError, ValueError):
                return False
            self._pedidos.fijar_entrega(
                pedido["id"],
                pedido["tipo_entrega"],
                ahora,
                paso_siguiente="confirmacion",
                zona_domicilio=pedido["zona_domicilio"],
                latitud=latitud,
                longitud=longitud,
            )
        else:
            texto = _texto_entrante(mensaje)
            if texto is None or not texto.strip():
                return False
            self._pedidos.fijar_entrega(
                pedido["id"],
                pedido["tipo_entrega"],
                ahora,
                paso_siguiente="confirmacion",
                zona_domicilio=pedido["zona_domicilio"],
                direccion_texto=texto.strip(),
            )

        self._enviar_resumen_y_confirmacion(numero, self._pedidos.obtener_en_construccion(numero))
        return True

    def _manejar_confirmacion(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "button_reply":
            return False

        if id_interactivo == ID_BOTON_CONFIRMAR:
            self._pedidos.fijar_paso(pedido["id"], "metodo_pago", ahora)
            self._pedir_metodo_pago(numero)
            return True

        if id_interactivo == ID_BOTON_CAMBIAR:
            self._pedidos.vaciar_items(pedido["id"], ahora)
            self._enviar_menu(numero, "Elija de nuevo los productos de su pedido:")
            return True
        return False

    def _manejar_metodo_pago(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo != "button_reply":
            return False

        if id_interactivo == ID_BOTON_PAGO_EFECTIVO:
            self._confirmar_pago_efectivo(numero, pedido, ahora)
            return True

        if id_interactivo == ID_BOTON_PAGO_QR:
            _, total = _construir_resumen(pedido, self._domicilio)
            self._pedidos.marcar_pago_pendiente(pedido["id"], total, ahora)
            logger.info(
                "Pedido #%s: método de pago QR, queda en pago_pendiente (remitente=%s)",
                pedido["id"], enmascarar_numero(numero),
            )
            self._pedir_comprobante(numero, pedido["id"], total)
            return True
        return False

    def _manejar_pago_pendiente(self, numero, pedido, mensaje, ahora) -> bool:
        tipo_interactivo, id_interactivo = _tipo_e_id_interactivo(mensaje)
        if tipo_interactivo == "button_reply" and id_interactivo == ID_BOTON_PAGO_EFECTIVO:
            self._confirmar_pago_efectivo(numero, pedido, ahora)
            return True

        tipo_mensaje = mensaje.get("type")
        if tipo_mensaje == "image":
            self._pedidos.marcar_pago_por_verificar(pedido["id"], ahora)
            logger.info(
                "Pedido #%s: comprobante recibido, pasa a verificación (remitente=%s)",
                pedido["id"], enmascarar_numero(numero),
            )
            self._enviar_texto(numero, MENSAJE_COMPROBANTE_RECIBIDO)
            self._avisar_dueno(pedido, mensaje)
            return True

        if tipo_mensaje == "document":
            self._pedidos.tocar(pedido["id"], ahora)
            self._enviar_texto(numero, MENSAJE_DOCUMENTO_EN_PAGO_PENDIENTE)
            return True

        if _texto_entrante(mensaje) is not None:
            self._pedidos.tocar(pedido["id"], ahora)
            self._pedir_comprobante(numero, pedido["id"], pedido["total"])
            return True
        return False

    def _manejar_pago_por_verificar(self, numero, pedido, mensaje, ahora) -> bool:
        self._pedidos.tocar(pedido["id"], ahora)
        self._enviar_texto(numero, MENSAJE_PAGO_EN_VERIFICACION)
        return True
