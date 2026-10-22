"""Migraciones Alembic, composición con Pillow y validación de la configuración."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import inspect

from app.config import Settings
from app.dominio.composicion import (
    Compositor,
    DibujoInvalido,
    RecortadorUmbral,
    abrir_dibujo,
    fondo_del_banco,
)
from app.infra.bd import crear_motor
from app.infra.orm import Base
from tests.conftest import dibujo_png

RAIZ = Path(__file__).resolve().parent.parent


def _columnas(url: str) -> dict[str, set[str]]:
    async def _leer():
        motor = crear_motor(url)
        async with motor.connect() as conexion:

            def _sync(c):
                ins = inspect(c)
                return {
                    t: {col["name"] for col in ins.get_columns(t)} for t in ins.get_table_names()
                }

            datos = await conexion.run_sync(_sync)
        await motor.dispose()
        return datos

    return asyncio.run(_leer())


def test_migracion_coincide_con_los_modelos(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'mig.db').as_posix()}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configurar_logs"] = False
    command.upgrade(cfg, "head")

    tablas = _columnas(url)
    tablas.pop("alembic_version")
    esperado = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}
    assert tablas == esperado

    command.downgrade(cfg, "base")
    assert set(_columnas(url)) == {"alembic_version"}


def test_dibujo_transparente_recibe_fondo_blanco():
    png = abrir_dibujo(dibujo_png(transparente=True))
    img = Image.open(io.BytesIO(png))
    assert img.mode == "RGB"
    assert img.getpixel((0, 0)) == (255, 255, 255)


def test_dibujo_invalido():
    with pytest.raises(DibujoInvalido):
        abrir_dibujo(b"GIF89a no")


def test_recorte_y_composicion():
    compositor = Compositor(RecortadorUmbral())
    recorte = Image.open(io.BytesIO(compositor.recortar(abrir_dibujo(dibujo_png()))))
    assert recorte.mode == "RGBA"
    assert recorte.size[0] < 400 and recorte.size[1] < 300  # recortado al contenido
    assert recorte.getpixel((0, 0))[3] == 0  # esquina transparente

    buf = io.BytesIO()
    recorte.save(buf, format="PNG")
    pagina = Image.open(io.BytesIO(compositor.componer(fondo_del_banco(0), buf.getvalue(), 2)))
    assert pagina.size == (1024, 1024)
    # El trazo rojo del dibujo aparece en la página compuesta.
    rojos = sum(1 for p in pagina.getdata() if p[0] > 180 and p[1] < 80 and p[2] < 80)
    assert rojos > 100


def _base(**cambios):
    datos = dict(
        jwt_secreto="s" * 48,
        proveedor_vision="falso",
        proveedor_texto="falso",
        proveedor_moderacion="falso",
        proveedor_imagen="falso",
        proveedor_voz="falso",
        proveedor_correo="falso",
        almacen="memoria",
    )
    datos.update(cambios)
    return Settings(_env_file=None, **datos)


def test_configuracion_falla_al_arrancar_si_falta_algo():
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        _base(proveedor_texto="openai")
    with pytest.raises(ValidationError, match="ELEVENLABS"):
        _base(proveedor_voz="elevenlabs")
    with pytest.raises(ValidationError, match="falsos"):
        _base(entorno="produccion")
    with pytest.raises(ValidationError):
        _base(jwt_secreto="corto")


def test_valores_por_defecto_de_los_modelos():
    s = _base()
    assert s.openai_modelo_imagen == "gpt-image-1-mini"
    assert s.openai_calidad_imagen == "low" and s.openai_tamano_imagen == "1024x1024"
    assert s.openai_modelo_moderacion == "omni-moderation-latest"
    assert s.elevenlabs_modelo == "eleven_flash_v2_5"
