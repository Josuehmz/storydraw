# Imagen única de la API (uvicorn/ASGI). Escala en horizontal: no guarda estado local.
#
# Por defecto es la de producción (Render Free, 512 MB): sin rembg ni onnxruntime, con
# RECORTE=umbral. Para el recorte con rembg (docker compose local): --build-arg CON_REMBG=1.
FROM python:3.12-slim

ARG CON_REMBG=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    U2NET_HOME=/app/.u2net

WORKDIR /app

COPY requirements.txt requirements-rembg.txt ./
RUN pip install -r requirements.txt

# libgomp1: la necesita onnxruntime (rembg)
RUN if [ "$CON_REMBG" = "1" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends libgomp1 \
        && rm -rf /var/lib/apt/lists/* \
        && pip install -r requirements-rembg.txt; \
    fi

COPY alembic.ini pyproject.toml ./
COPY alembic ./alembic
COPY app ./app

# Usuario sin privilegios. /app/.u2net es donde rembg guarda su modelo (solo con CON_REMBG=1).
RUN useradd --create-home --uid 1000 storydraw \
    && mkdir -p /app/.u2net && chown -R storydraw /app
USER storydraw

EXPOSE 8000

# Migra el esquema y arranca. PORT lo inyecta el PaaS (Render); en local es 8000.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
