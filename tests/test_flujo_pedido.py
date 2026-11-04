from flujo_pedido import MENSAJE_CANCELADO_POR_CLIENTE, FlujoPedido
from pedidos import Pedidos

CATALOGO = {
    "tamal_sencillo": {"nombre": "Tamal sencillo", "precio": 8000, "unidad": "unidad"},
    "tamal_especial": {"nombre": "Tamal especial", "precio": 12000, "unidad": "unidad"},
    "bebida": {"nombre": "Bebida", "precio": 3000, "unidad": "unidad"},
}
DOMICILIO = {
    "pedido_minimo": 15000,
    "centro": {"nombre": "Centro", "costo": 3000, "tiempo_estimado": "20-30 minutos"},
    "la_estacion": {"nombre": "La Estación", "costo": 4000, "tiempo_estimado": "30-45 minutos"},
}
MENSAJE_DERIVACION = "Le comunico con una persona de nuestro equipo."


class EnviosTexto:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, texto):
        self.llamadas.append((numero, texto))
        return True


class EnviosBotones:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, texto_cuerpo, botones):
        self.llamadas.append((numero, texto_cuerpo, botones))
        return True


class EnviosLista:
    def __init__(self):
        self.llamadas = []

    def __call__(self, numero, texto_cuerpo, texto_boton, secciones):
        self.llamadas.append((numero, texto_cuerpo, texto_boton, secciones))
        return True


def _crear_flujo(tmp_path, reloj=lambda: 1000.0, catalogo=None, domicilio=None):
    pedidos = Pedidos(tmp_path / "pedidos.db")
    texto, botones, lista = EnviosTexto(), EnviosBotones(), EnviosLista()
    flujo = FlujoPedido(
        pedidos=pedidos,
        catalogo=catalogo if catalogo is not None else CATALOGO,
        domicilio=domicilio if domicilio is not None else DOMICILIO,
        mensaje_derivacion=MENSAJE_DERIVACION,
        enviar_texto_fn=texto,
        enviar_botones_fn=botones,
        enviar_lista_fn=lista,
        reloj=reloj,
    )
    return flujo, pedidos, texto, botones, lista


def _mensaje_texto(texto):
    return {"type": "text", "text": {"body": texto}}


def _mensaje_boton(id_boton):
    return {"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": id_boton, "title": "x"}}}


def _mensaje_lista(id_fila):
    return {
        "type": "interactive",
        "interactive": {"type": "list_reply", "list_reply": {"id": id_fila, "title": "x", "description": ""}},
    }


def _mensaje_ubicacion(lat, lon):
    return {"type": "location", "location": {"latitude": lat, "longitude": lon}}


def test_flujo_completo_un_producto_recoger_en_local(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"

    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    assert texto.llamadas[-1] == (numero, '¿Cuántas unidades de "Tamal sencillo" desea (1 a 50)?')

    flujo.manejar_mensaje(numero, _mensaje_texto("2"))
    assert "Agregado: 2" in botones.llamadas[-1][1]

    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    assert "¿Cómo desea recibir su pedido?" in botones.llamadas[-1][1]

    flujo.manejar_mensaje(numero, _mensaje_boton("recoger_local"))
    # Recoger en el local: nunca se pide consentimiento, no hace falta dirección.
    assert "Entrega: Recoger en el local." in botones.llamadas[-1][1]
    assert "Total: $16.000" in botones.llamadas[-1][1]
    assert "Ley 1581" not in "\n".join(llamada[1] for llamada in botones.llamadas)

    flujo.manejar_mensaje(numero, _mensaje_boton("confirmar"))
    assert "Pedido #" in texto.llamadas[-1][1]
    assert "recibido" in texto.llamadas[-1][1]
    assert "Entrega: Recoger en el local." in texto.llamadas[-1][1]
    assert pedidos.obtener_en_construccion(numero) is None


def test_el_total_siempre_sale_del_catalogo_nunca_de_un_texto_libre(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"

    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_especial"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))  # 2 x 12.000 = 24.000, siempre desde el catálogo
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("recoger_local"))

    assert "Total: $24.000" in botones.llamadas[-1][1]


def test_varios_productos_y_domicilio_total_correcto(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"

    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))  # 16.000
    flujo.manejar_mensaje(numero, _mensaje_boton("agregar_otro"))
    assert lista.llamadas[-1][0] == numero

    flujo.manejar_mensaje(numero, _mensaje_lista("bebida"))
    flujo.manejar_mensaje(numero, _mensaje_texto("1"))  # 3.000 -> subtotal 19.000
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))
    # Subtotal (19.000) ya alcanza el pedido mínimo (15.000): pide consentimiento.
    assert "Ley 1581" in botones.llamadas[-1][1]

    flujo.manejar_mensaje(numero, _mensaje_boton("acepto_datos"))
    assert lista.llamadas[-1][2] == "Ver zonas"

    flujo.manejar_mensaje(numero, _mensaje_lista("centro"))
    flujo.manejar_mensaje(numero, _mensaje_texto("Calle 1 # 2-3"))
    # 16.000 + 3.000 + domicilio centro 3.000 = 22.000
    assert "Entrega: Domicilio - Centro" in botones.llamadas[-1][1]
    assert "Dirección: Calle 1 # 2-3" in botones.llamadas[-1][1]
    assert "Total: $22.000" in botones.llamadas[-1][1]

    flujo.manejar_mensaje(numero, _mensaje_boton("confirmar"))
    assert "Entrega: Domicilio - Centro" in texto.llamadas[-1][1]
    assert "Dirección: Calle 1 # 2-3" in texto.llamadas[-1][1]
    assert "Tiempo estimado: 20-30 minutos." in texto.llamadas[-1][1]
    assert pedidos.obtener_en_construccion(numero) is None


def test_pedido_minimo_no_alcanzado_ofrece_agregar_otro_o_recoger(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"

    flujo.iniciar(numero, "tamales", _mensaje_lista("bebida"))
    flujo.manejar_mensaje(numero, _mensaje_texto("1"))  # 3.000, bajo el mínimo de 15.000
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))

    assert "pedido mínimo" in botones.llamadas[-1][1].lower()
    # El mínimo no se alcanzó: nunca se llegó a pedir consentimiento.
    assert "Ley 1581" not in "\n".join(llamada[1] for llamada in botones.llamadas)
    ids_ofrecidos = {b["id"] for b in botones.llamadas[-1][2]}
    assert ids_ofrecidos == {"agregar_otro", "recoger_local"}

    flujo.manejar_mensaje(numero, _mensaje_boton("recoger_local"))
    assert "Total: $3.000" in botones.llamadas[-1][1]


def test_producto_inventado_en_la_lista_se_ignora_y_reenvia_el_menu(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)

    flujo.manejar_mensaje(numero, _mensaje_lista("producto_que_no_existe"))

    assert "No entendí esa respuesta" in texto.llamadas[-1][1]
    assert "cancelar" in texto.llamadas[-1][1].lower()
    # Se reenvía el mismo menú (lista), no un mensaje de botones genérico.
    assert lista.llamadas[-1][0] == numero
    assert lista.llamadas[-1][2] == "Ver menú"
    assert botones.llamadas == []
    # El pedido sigue en construcción: la entrada inválida no lo cancela.
    assert pedidos.obtener_en_construccion(numero) is not None


def test_zona_inventada_se_ignora_y_reenvia_la_lista_de_zonas(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    id_pedido = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.agregar_item(id_pedido, "bebida", "Bebida", 3000, 10, ahora=1001.0)
    pedidos.fijar_consentimiento(id_pedido, True, ahora=1002.0, paso_siguiente="zona")

    flujo.manejar_mensaje(numero, _mensaje_lista("zona_que_no_existe"))

    assert "No entendí esa respuesta" in texto.llamadas[-1][1]
    assert lista.llamadas[-1][2] == "Ver zonas"


def test_cantidad_invalida_se_repregunta_en_vez_de_mensaje_generico(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))

    flujo.manejar_mensaje(numero, _mensaje_texto("cero"))
    assert "entre 1 y 50" in texto.llamadas[-1][1]
    assert botones.llamadas == []

    flujo.manejar_mensaje(numero, _mensaje_texto("100"))
    assert "entre 1 y 50" in texto.llamadas[-1][1]

    flujo.manejar_mensaje(numero, _mensaje_texto("3"))
    assert "Agregado: 3" in botones.llamadas[-1][1]


def test_consentimiento_rechazado_no_cancela_sino_que_ofrece_recoger_o_cancelar(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))  # 16.000, alcanza el pedido mínimo (15.000)
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))

    flujo.manejar_mensaje(numero, _mensaje_boton("no_acepto_datos"))

    assert botones.llamadas[-1][1] == (
        "Entendido, sin su dirección no podemos llevarle el pedido. ¿Prefiere recogerlo en el local?"
    )
    ids_ofrecidos = [b["id"] for b in botones.llamadas[-1][2]]
    assert ids_ofrecidos == ["recoger_local", "cancelar"]
    # No se cancela: el pedido sigue en construcción, a la espera de esa elección.
    assert pedidos.obtener_en_construccion(numero) is not None


def test_tras_rechazar_consentimiento_recoger_en_el_local_lleva_al_resumen_sin_direccion(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))  # 16.000, alcanza el pedido mínimo (15.000)
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))
    flujo.manejar_mensaje(numero, _mensaje_boton("no_acepto_datos"))

    flujo.manejar_mensaje(numero, _mensaje_boton("recoger_local"))

    assert "Entrega: Recoger en el local." in botones.llamadas[-1][1]
    assert "¿Confirma su pedido?" in botones.llamadas[-1][1]
    pedido = pedidos.obtener_en_construccion(numero)
    assert pedido["tipo_entrega"] == "recoger"
    assert pedido["direccion_texto"] is None
    assert pedido["latitud"] is None
    assert pedido["zona_domicilio"] is None


def test_tras_rechazar_consentimiento_cancelar_cancela_con_mensaje_amable(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))  # 16.000, alcanza el pedido mínimo (15.000)
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))
    flujo.manejar_mensaje(numero, _mensaje_boton("no_acepto_datos"))

    flujo.manejar_mensaje(numero, _mensaje_boton("cancelar"))

    assert texto.llamadas[-1] == (numero, MENSAJE_CANCELADO_POR_CLIENTE)
    assert pedidos.obtener_en_construccion(numero) is None


def test_tras_rechazar_consentimiento_la_palabra_clave_asesor_sigue_funcionando(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))  # 16.000, alcanza el pedido mínimo (15.000)
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))
    flujo.manejar_mensaje(numero, _mensaje_boton("no_acepto_datos"))

    flujo.manejar_mensaje(numero, _mensaje_texto("asesor"))

    assert texto.llamadas[-1] == (numero, MENSAJE_DERIVACION)
    assert pedidos.obtener_en_construccion(numero) is None


def test_cancelar_por_palabra_clave_a_mitad_del_pedido(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))

    flujo.manejar_mensaje(numero, _mensaje_texto("cancelar"))

    assert pedidos.obtener_en_construccion(numero) is None
    assert "cancelado" in texto.llamadas[-1][1].lower()


def test_pedir_hablar_con_una_persona_a_mitad_del_pedido_deriva_y_cancela(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))

    flujo.manejar_mensaje(numero, _mensaje_texto("asesor"))

    assert texto.llamadas[-1] == (numero, MENSAJE_DERIVACION)
    assert pedidos.obtener_en_construccion(numero) is None


def test_boton_cancelar_sigue_cancelando_el_pedido_donde_sea_que_aparezca(tmp_path):
    # El id "cancelar" ya no se ofrece en el mensaje de "entrada no reconocida"
    # (ahora se reenvía el paso actual en su lugar), pero sigue existiendo en
    # los botones de la confirmación [Confirmar][Cambiar][Cancelar], y el
    # manejo es global: debe cancelar sin importar en qué paso llegue.
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_lista("producto_que_no_existe"))  # entrada no reconocida

    flujo.manejar_mensaje(numero, _mensaje_boton("cancelar"))

    assert pedidos.obtener_en_construccion(numero) is None


def test_boton_seguir_con_el_pedido_sigue_siendo_inofensivo_si_llega(tmp_path):
    # Ya no se ofrece este botón, pero si llegara (por ejemplo desde una
    # conversación vieja que todavía lo tiene visible), no debe cancelar nada.
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_lista("producto_que_no_existe"))  # entrada no reconocida

    flujo.manejar_mensaje(numero, _mensaje_boton("seguir_pedido"))
    assert pedidos.obtener_en_construccion(numero) is not None

    flujo.manejar_mensaje(numero, _mensaje_texto("3"))
    assert "Agregado: 3" in botones.llamadas[-1][1]


def test_timeout_de_30_minutos_cancela_el_pedido(tmp_path):
    ahora = {"valor": 1000.0}
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path, reloj=lambda: ahora["valor"])
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))

    ahora["valor"] += 30 * 60 + 1
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))

    assert pedidos.obtener_en_construccion(numero) is None
    assert "30 minutos" in texto.llamadas[-1][1]


def test_sin_llegar_al_timeout_el_pedido_sigue_en_construccion(tmp_path):
    ahora = {"valor": 1000.0}
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path, reloj=lambda: ahora["valor"])
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))

    ahora["valor"] += 30 * 60 - 5
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))

    assert pedidos.obtener_en_construccion(numero) is not None
    assert "Agregado: 2" in botones.llamadas[-1][1]


def test_direccion_por_ubicacion_compartida(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("bebida"))
    flujo.manejar_mensaje(numero, _mensaje_texto("10"))  # 30.000, sobre el mínimo
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))
    flujo.manejar_mensaje(numero, _mensaje_boton("acepto_datos"))
    flujo.manejar_mensaje(numero, _mensaje_lista("centro"))

    flujo.manejar_mensaje(numero, _mensaje_ubicacion(4.7, -74.2))

    assert "Dirección: ubicación compartida por WhatsApp" in botones.llamadas[-1][1]
    assert "¿Confirma su pedido?" in botones.llamadas[-1][1]


def test_cambiar_en_confirmacion_vacia_el_pedido_y_vuelve_a_elegir_productos(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("1"))
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("recoger_local"))

    flujo.manejar_mensaje(numero, _mensaje_boton("cambiar"))

    pedido = pedidos.obtener_en_construccion(numero)
    assert pedido["items"] == []
    assert pedido["paso"] == "producto"

    flujo.manejar_mensaje(numero, _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("1"))
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    assert "¿Cómo desea recibir su pedido?" in botones.llamadas[-1][1]


def test_domicilio_tras_cambiar_vuelve_a_pedir_consentimiento(tmp_path):
    # El consentimiento ya no se recuerda entre intentos: se pide cada vez que
    # se entra a la rama de domicilio con el mínimo alcanzado, aunque antes ya
    # se hubiera aceptado para un domicilio anterior en el mismo pedido.
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("bebida"))
    flujo.manejar_mensaje(numero, _mensaje_texto("10"))  # 30.000, sobre el mínimo
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))
    flujo.manejar_mensaje(numero, _mensaje_boton("acepto_datos"))
    flujo.manejar_mensaje(numero, _mensaje_lista("centro"))
    flujo.manejar_mensaje(numero, _mensaje_texto("Calle 1 # 2-3"))
    flujo.manejar_mensaje(numero, _mensaje_boton("cambiar"))

    flujo.manejar_mensaje(numero, _mensaje_lista("bebida"))
    flujo.manejar_mensaje(numero, _mensaje_texto("10"))
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))

    assert "Ley 1581" in botones.llamadas[-1][1]


def test_dos_numeros_con_pedidos_simultaneos_no_se_mezclan(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero_a = "573001112233"
    numero_b = "573009998877"

    flujo.iniciar(numero_a, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.iniciar(numero_b, "tamales", _mensaje_lista("bebida"))

    flujo.manejar_mensaje(numero_a, _mensaje_texto("2"))
    flujo.manejar_mensaje(numero_b, _mensaje_texto("5"))

    pedido_a = pedidos.obtener_en_construccion(numero_a)
    pedido_b = pedidos.obtener_en_construccion(numero_b)
    assert pedido_a["items"][0]["clave_producto"] == "tamal_sencillo"
    assert pedido_a["items"][0]["cantidad"] == 2
    assert pedido_b["items"][0]["clave_producto"] == "bebida"
    assert pedido_b["items"][0]["cantidad"] == 5


def test_texto_no_reconocido_en_paso_de_botones_reenvia_los_mismos_botones(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    id_pedido = pedidos.crear_en_construccion(numero, "tamales", ahora=1000.0)
    pedidos.agregar_item(id_pedido, "tamal_sencillo", "Tamal sencillo", 8000, 1, ahora=1001.0)
    pedidos.fijar_paso(id_pedido, "entrega", ahora=1003.0)

    flujo.manejar_mensaje(numero, _mensaje_texto("no sé qué escribir"))

    assert "No entendí esa respuesta" in texto.llamadas[-1][1]
    assert "cancelar" in texto.llamadas[-1][1].lower()
    assert botones.llamadas[-1][1] == "¿Cómo desea recibir su pedido?"
    ids_ofrecidos = [b["id"] for b in botones.llamadas[-1][2]]
    assert ids_ofrecidos == ["domicilio", "recoger_local"]
    assert len(ids_ofrecidos) <= 3  # límite de WhatsApp para botones


def test_texto_no_reconocido_en_confirmacion_reenvia_el_resumen_completo(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("acepto_datos"))
    flujo.manejar_mensaje(numero, _mensaje_boton("recoger_local"))

    flujo.manejar_mensaje(numero, _mensaje_texto("¿cuánto se demora?"))

    assert "No entendí esa respuesta" in texto.llamadas[-1][1]
    assert "Total: $16.000" in botones.llamadas[-1][1]
    assert "¿Confirma su pedido?" in botones.llamadas[-1][1]
    ids_ofrecidos = [b["id"] for b in botones.llamadas[-1][2]]
    assert ids_ofrecidos == ["confirmar", "cambiar", "cancelar"]
    assert len(ids_ofrecidos) <= 3


def test_pedido_conserva_los_productos_elegidos_tras_texto_no_reconocido(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))  # agrega el producto, paso -> agregar_otro_o_continuar

    flujo.manejar_mensaje(numero, _mensaje_texto("una pregunta rara"))  # texto no reconocido en ese paso

    pedido = pedidos.obtener_en_construccion(numero)
    assert pedido["items"] == [
        {
            "clave_producto": "tamal_sencillo",
            "nombre": "Tamal sencillo",
            "precio_unitario": 8000,
            "cantidad": 2,
            "subtotal": 16000,
        }
    ]
    # Y el menú de "agregar otro / continuar" se reenvía, sin perder lo elegido.
    assert botones.llamadas[-1][1] == "¿Desea agregar algo más a su pedido?"


def test_palabras_clave_de_cancelar_y_persona_funcionan_con_mayusculas_y_tildes(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero_a = "573001112233"
    numero_b = "573009998877"

    flujo.iniciar(numero_a, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero_a, _mensaje_texto("Cancelar"))
    assert pedidos.obtener_en_construccion(numero_a) is None
    assert "cancelado" in texto.llamadas[-1][1].lower()

    flujo.iniciar(numero_b, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero_b, _mensaje_texto("ASESOR"))
    assert pedidos.obtener_en_construccion(numero_b) is None
    assert texto.llamadas[-1] == (numero_b, MENSAJE_DERIVACION)


def test_frase_hablar_con_alguien_deriva_y_cancela(tmp_path):
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))

    flujo.manejar_mensaje(numero, _mensaje_texto("Hablar con alguien"))

    assert texto.llamadas[-1] == (numero, MENSAJE_DERIVACION)
    assert pedidos.obtener_en_construccion(numero) is None


def test_el_logging_enmascara_el_numero_y_no_incluye_direccion_ni_texto_del_cliente(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="flujo_pedido")
    flujo, pedidos, texto, botones, lista = _crear_flujo(tmp_path)
    numero = "573001112233"
    direccion_secreta = "Calle Secreta # 99-99, apto 404"

    flujo.iniciar(numero, "tamales", _mensaje_lista("tamal_sencillo"))
    flujo.manejar_mensaje(numero, _mensaje_texto("2"))
    flujo.manejar_mensaje(numero, _mensaje_boton("continuar"))
    flujo.manejar_mensaje(numero, _mensaje_boton("domicilio"))
    flujo.manejar_mensaje(numero, _mensaje_boton("acepto_datos"))
    flujo.manejar_mensaje(numero, _mensaje_lista("centro"))
    flujo.manejar_mensaje(numero, _mensaje_texto(direccion_secreta))
    flujo.manejar_mensaje(numero, _mensaje_boton("confirmar"))

    mensajes = "\n".join(registro.getMessage() for registro in caplog.records)
    assert numero not in mensajes
    assert mensajes.count(numero[-4:]) >= 1  # los últimos 4 dígitos sí pueden aparecer (enmascarado)
    assert direccion_secreta not in mensajes
    assert "confirmado" in mensajes.lower()
