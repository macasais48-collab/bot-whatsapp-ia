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
    cerebro.py \
    env.py \
    historial.py \
    media_cache.py \
    mensajes_enriquecidos.py \
    negocio.md \
    perfil_camilo.md \
    recursos.py \
    recursos_camilo.json \
    recursos_panaderia.json \
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

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--worker-tmp-dir", "/tmp", "--no-control-socket", "webhook:crear_app()"]
