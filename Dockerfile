FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/datos \
    && chown -R appuser:appuser /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser \
    almacenamiento.py \
    basedatos.py \
    cerebro.py \
    env.py \
    estado_pedido.py \
    flujo_pedido.py \
    gestionar_pedido.py \
    gunicorn.conf.py \
    historial.py \
    media_cache.py \
    mensajes_enriquecidos.py \
    negocio.md \
    pago_pedido.py \
    pedido_resumen.py \
    pedidos.py \
    perfil_camilo.md \
    perfil_tamales.md \
    perfiles_negocio.py \
    recursos.py \
    recursos_camilo.json \
    recursos_panaderia.json \
    recursos_tamales.json \
    red_meta.py \
    telefono.py \
    webhook.py \
    whatsapp.py \
    ./
COPY --chown=appuser:appuser llm/ ./llm/
COPY --chown=appuser:appuser recursos/demo/ ./recursos/demo/

VOLUME ["/app/datos"]

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=3)"

# --timeout 60: el default de gunicorn (30s) ya no alcanza con margen una vez
# que los envíos a WhatsApp reintentan ante 429/errores de conexión (ver
# whatsapp.py/mensajes_enriquecidos.py/media_cache.py) y el reenvío del
# comprobante al dueño hace varias llamadas HTTP seguidas a Meta: 60s cubre el
# peor caso realista (IA + envío con reintentos + reenvío de media) sin dejar
# un hilo colgado indefinidamente si algo se cuelga de verdad.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "1", "--threads", "12", "--timeout", "60", "--worker-tmp-dir", "/tmp", "--no-control-socket", "webhook:crear_app()"]
