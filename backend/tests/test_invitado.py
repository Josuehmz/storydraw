"""Modo invitado (solo pruebas locales): apagado por defecto, prohibido en producción,
con moderación y sin dejar el cuento en el servidor."""

from __future__ import annotations

import asyncio
import base64
import io

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import func, select

from app.config import Settings
from app.infra.orm import Cuento, Pagina, RegistroModeracion
from tests.conftest import dibujo_png
from tests.test_moderacion import _cuento_malo


def _entrar(entorno) -> dict[str, str]:
    r = entorno.cliente.post("/v1/invitado")
    assert r.status_code == 201, r.text
    assert r.json()["rol"] == "invitado"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _crear(entorno, cab, edad: int = 8, personaje: str | None = "un dragón"):
    datos: dict[str, str] = {"edad": str(edad)}
    if personaje is not None:
        datos["personaje"] = personaje
    return entorno.cliente.post(
        "/v1/invitado/cuentos",
        data=datos,
        files={"dibujo": ("dibujo.png", dibujo_png(), "image/png")},
        headers=cab,
    )


def _filas(entorno, modelo) -> int:
    async def contar() -> int:
        async with entorno.c.fabrica() as s:
            return (await s.execute(select(func.count()).select_from(modelo))).scalar_one()

    return asyncio.run(contar())


def _produccion(**cambios) -> Settings:
    datos = dict(
        entorno="produccion",
        jwt_secreto="s" * 48,
        openai_api_key="clave-de-prueba",
        smtp_host="smtp.ejemplo.com",
        smtp_remitente="hola@ejemplo.com",
        s3_access_key="acceso",
        s3_secret_key="secreto-s3",
    )
    datos.update(cambios)
    return Settings(_env_file=None, **datos)


def test_apagado_por_defecto(entorno):
    assert entorno.c.settings.permitir_invitados is False
    assert entorno.cliente.post("/v1/invitado").status_code == 404
    assert _crear(entorno, {}).status_code == 404


def test_produccion_rechaza_invitados():
    assert _produccion().permitir_invitados is False
    with pytest.raises(ValidationError, match="PERMITIR_INVITADOS"):
        _produccion(permitir_invitados=True)


def test_cuento_de_invitado_se_entrega_entero_y_no_queda_en_el_servidor(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True)
    cab = _entrar(entorno)

    r = _crear(entorno, cab, edad=7)
    assert r.status_code == 202, r.text
    cuento_id = r.json()["id"]

    cuento = entorno.cliente.get(f"/v1/invitado/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo"
    assert cuento["titulo"] and cuento["personaje"] == "un dragón"
    assert [p["numero"] for p in cuento["paginas"]] == [1, 2, 3]
    for p in cuento["paginas"]:
        imagen = Image.open(io.BytesIO(base64.b64decode(p["imagen_png_base64"])))
        assert imagen.format == "PNG"

    # Nada en la base de datos ni en el almacén, y el servidor ya lo olvidó.
    assert _filas(entorno, Cuento) == 0
    assert _filas(entorno, Pagina) == 0
    assert _filas(entorno, RegistroModeracion) == 0
    assert entorno.c.almacen.objetos == {}
    assert len(entorno.c.invitados) == 0
    assert entorno.cliente.get(f"/v1/invitado/cuentos/{cuento_id}", headers=cab).status_code == 404


def test_nombre_del_personaje_llega_al_cuento_del_invitado(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True)
    cab = _entrar(entorno)
    r = entorno.cliente.post(
        "/v1/invitado/cuentos",
        data={"edad": "8", "personaje": "un dragón", "nombre": "Rayo"},
        files={"dibujo": ("dibujo.png", dibujo_png(), "image/png")},
        headers=cab,
    )
    assert r.status_code == 202, r.text
    cuento = entorno.cliente.get(f"/v1/invitado/cuentos/{r.json()['id']}", headers=cab).json()
    assert cuento["estado"] == "listo"
    assert "Rayo" in cuento["paginas"][0]["texto"]


def test_la_moderacion_tambien_aplica_al_invitado(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True)
    cab = _entrar(entorno)
    entorno.c.texto.cuentos_forzados = [_cuento_malo() for _ in range(3)]

    cuento_id = _crear(entorno, cab).json()["id"]
    cuento = entorno.cliente.get(f"/v1/invitado/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "rechazado"
    assert cuento["paginas"] == [] and cuento["titulo"] is None
    assert entorno.c.almacen.objetos == {}
    assert _filas(entorno, RegistroModeracion) == 0


def test_entrada_del_invitado_moderada(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True)
    cab = _entrar(entorno)
    cuento_id = _crear(entorno, cab, personaje="un monstruo malvado").json()["id"]
    cuento = entorno.cliente.get(f"/v1/invitado/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "rechazado"
    assert entorno.c.texto.llamadas_cuento == 0


def test_token_de_invitado_no_abre_rutas_de_cuenta_ni_al_reves(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True)
    invitado = _entrar(entorno)
    assert entorno.cliente.get("/v1/perfiles", headers=invitado).status_code == 401
    tutor = entorno.registrar("a@correo.com")
    assert _crear(entorno, tutor).status_code == 401
    assert _crear(entorno, {}).status_code == 401


def test_un_invitado_no_ve_el_cuento_de_otro(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True)
    a, b = _entrar(entorno), _entrar(entorno)
    cuento_id = _crear(entorno, a).json()["id"]
    assert entorno.cliente.get(f"/v1/invitado/cuentos/{cuento_id}", headers=b).status_code == 404
    assert entorno.cliente.get(f"/v1/invitado/cuentos/{cuento_id}", headers=a).status_code == 200


def test_edad_fuera_de_rango(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True)
    cab = _entrar(entorno)
    assert _crear(entorno, cab, edad=5).status_code == 422
    assert _crear(entorno, cab, edad=13).status_code == 422


def test_limite_por_ip_para_invitados(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True, limite_invitado_ip="2/minute")
    cab = _entrar(entorno)
    estados = [_crear(entorno, cab).status_code for _ in range(3)]
    assert estados == [202, 202, 429]
    # Otro token desde la misma IP no se salta el límite.
    assert _crear(entorno, _entrar(entorno)).status_code == 429
