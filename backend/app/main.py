"""Punto de entrada: `uvicorn app.main:create_app --factory`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api import limites
from app.api.rutas import auth, cuentos, operacion, perfiles
from app.config import Settings, obtener_settings
from app.contenedor import Contenedor, construir
from app.infra.adaptadores.almacen import AlmacenS3

log = logging.getLogger("storydraw")


def create_app(settings: Settings | None = None, contenedor: Contenedor | None = None) -> FastAPI:
    settings = settings or obtener_settings()
    c = contenedor or construir(settings)
    limites.configurar(
        settings.limite_auth,
        settings.limite_identificar,
        settings.limite_cuentos_ip,
        settings.limite_cuentos_cuenta,
    )

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        if isinstance(c.almacen, AlmacenS3) and settings.entorno != "produccion":
            try:
                await c.almacen.asegurar_bucket()
            except Exception:
                log.warning("No se pudo comprobar el bucket %s", settings.s3_bucket)
        yield
        await c.cerrar()

    app = FastAPI(
        title="StoryDraw API",
        version="0.1.0",
        description="Del dibujo de un niño a un cuento ilustrado y narrado.",
        lifespan=ciclo_de_vida,
        docs_url=None if settings.entorno == "produccion" else "/docs",
        redoc_url=None,
    )
    app.state.contenedor = c
    app.state.limiter = limites.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    if settings.lista_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.lista_cors,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(auth.router)
    app.include_router(perfiles.router)
    app.include_router(cuentos.router)
    app.include_router(operacion.router)

    @app.get("/salud", tags=["salud"])
    async def salud() -> dict:
        try:
            async with c.motor.connect() as conexion:
                await conexion.execute(text("SELECT 1"))
            bd = "ok"
        except Exception:
            bd = "caida"
        return {
            "estado": "ok" if bd == "ok" else "degradado",
            "base_de_datos": bd,
            "proveedores": {
                "vision": c.vision.proveedor,
                "texto": c.texto.proveedor,
                "moderacion": c.moderador.proveedor,
                "imagen": c.imagen.proveedor,
                "voz": c.voz.proveedor,
                "correo": c.correo.proveedor,
            },
        }

    return app
