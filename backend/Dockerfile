# Imagen única de la API (uvicorn/ASGI). Escala en horizontal: no guarda estado local.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    U2NET_HOME=/app/.u2net

WORKDIR /app

# libgomp1: la necesita onnxruntime (rembg)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini pyproject.toml ./
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home --uid 10001 storydraw \
    && mkdir -p /app/.u2net && chown -R storydraw /app
USER storydraw

EXPOSE 8000

# Migra el esquema y arranca. PORT lo inyecta el PaaS; en local es 8000.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
