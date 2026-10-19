"""Fixtures: app con adaptadores falsos, SQLite temporal y almacén en memoria."""

from __future__ import annotations

import asyncio
import io
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import Settings
from app.contenedor import Contenedor, construir
from app.infra.bd import crear_motor
from app.infra.orm import Base
from app.main import create_app

CONTRASENA = "una-clave-larga-123"


def settings_de_prueba(ruta_bd: Path, **cambios) -> Settings:
    base = dict(
        entorno="pruebas",
        database_url=f"sqlite+aiosqlite:///{ruta_bd.as_posix()}",
        jwt_secreto="s" * 48,
        proveedor_vision="falso",
        proveedor_texto="falso",
        proveedor_moderacion="falso",
        proveedor_imagen="falso",
        proveedor_voz="falso",
        proveedor_correo="falso",
        almacen="memoria",
        recorte="umbral",
        reintentos_por_paso=1,
        espera_reintento_s=0,
        max_regeneraciones=2,
        admin_emails="admin@storydraw.com",
        contenido_emails="revisora@storydraw.com",
        limite_auth="1000/minute",
        limite_identificar="1000/minute",
        limite_cuentos_ip="1000/minute",
        limite_cuentos_cuenta="1000/minute",
    )
    base.update(cambios)
    return Settings(_env_file=None, **base)


async def _crear_tablas(url: str) -> None:
    motor = crear_motor(url)
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)
    await motor.dispose()


@dataclass
class Entorno:
    cliente: TestClient
    c: Contenedor

    def registrar(self, email: str, verificar: bool = True) -> dict[str, str]:
        r = self.cliente.post(
            "/v1/auth/registro",
            json={"email": email, "contrasena": CONTRASENA, "acepta_consentimiento": True},
        )
        assert r.status_code == 201, r.text
        if verificar:
            cuerpo = self.c.correo.enviados[-1][2]
            token = re.search(r"token=([\w\-\.]+)", cuerpo).group(1)
            assert (
                self.cliente.get("/v1/auth/verificar", params={"token": token}).status_code == 200
            )
        r = self.cliente.post("/v1/auth/login", json={"email": email, "contrasena": CONTRASENA})
        if not verificar:
            return {}
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def crear_perfil(self, cabeceras: dict, apodo: str = "Luna", edad: int = 8) -> str:
        r = self.cliente.post(
            "/v1/perfiles", json={"apodo": apodo, "edad": edad}, headers=cabeceras
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def crear_cuento(self, cabeceras: dict, perfil_id: str, personaje: str | None = "un dragón"):
        datos = {"perfil_id": perfil_id}
        if personaje is not None:
            datos["personaje"] = personaje
        return self.cliente.post(
            "/v1/cuentos",
            data=datos,
            files={"dibujo": ("dibujo.png", dibujo_png(), "image/png")},
            headers=cabeceras,
        )


def dibujo_png(transparente: bool = False) -> bytes:
    fondo = (0, 0, 0, 0) if transparente else (255, 255, 255, 255)
    img = Image.new("RGBA", (400, 300), fondo)
    d = ImageDraw.Draw(img)
    d.ellipse([120, 60, 280, 220], outline=(200, 30, 30, 255), width=12)
    d.line([(200, 220), (200, 290)], fill=(20, 20, 20, 255), width=10)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()


@pytest.fixture
def crear_entorno(tmp_path) -> Iterator[Callable[..., Entorno]]:
    abiertos: list[TestClient] = []

    def _crear(**cambios) -> Entorno:
        settings = settings_de_prueba(tmp_path / f"bd{len(abiertos)}.db", **cambios)
        asyncio.run(_crear_tablas(settings.database_url))
        c = construir(settings)
        cliente = TestClient(create_app(settings, c))
        cliente.__enter__()
        abiertos.append(cliente)
        return Entorno(cliente, c)

    yield _crear
    for cliente in abiertos:
        cliente.__exit__(None, None, None)


@pytest.fixture
def entorno(crear_entorno) -> Entorno:
    return crear_entorno()
