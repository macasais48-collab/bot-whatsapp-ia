# Configuración de logging de gunicorn (se carga con --config). El resto
# (bind, workers, hilos, socket de control desactivado) sigue viniendo de los
# flags del CMD en el Dockerfile; aquí no se toca.

accesslog = "-"
errorlog = "-"
loglevel = "info"
# Sin cadena de consulta: la verificación del webhook de Meta pasa el
# verify_token por la URL (?hub.mode=...&hub.verify_token=...&hub.challenge=...)
# y nunca debe quedar en ningún log. %(U)s es solo la ruta, sin query string
# (a diferencia de %(r)s, que sí la incluiría).
access_log_format = '%(h)s "%(m)s %(U)s" %(s)s %(L)s'


def post_fork(server, worker):
    # Se ejecuta en cada worker, después del fork: sin esto, los logger.info()
    # de webhook.py y flujo_pedido.py no tienen ningún handler configurado bajo
    # gunicorn (logging.basicConfig solo corría con "python webhook.py" directo,
    # nunca con la fábrica webhook:crear_app() que usa gunicorn) y se perdían
    # en silencio.
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
