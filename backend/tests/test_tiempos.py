"""Tiempos: duración por etapa en el log, tope por llamada con un solo reintento y tope del
cuento entero. Nace del cuento de invitado que tardó 180 s el 2026-10-26."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx
import pytest

from app.config import Settings
from app.contenedor import TIEMPO_MAXIMO_CUENTO_S, _tiempo_maximo_cuento
from app.infra.adaptadores.falsos import ImagenFalsa, TextoFalso
from app.infra.adaptadores.proveedor_cloudflare import ClienteCloudflare, ImagenCloudflare
from tests.conftest import dibujo_png

ETAPAS_CUENTO = {
    "recorte",
    "identificar",
    "moderar_entrada",
    "escribir",
    "moderar_cuento",
    "fondo_1",
    "fondo_2",
    "fondo_3",
    "escenarios",
    "espera_recorte",
    "componer_1",
    "componer_2",
    "componer_3",
    "guardar_1",
    "guardar_2",
    "guardar_3",
    "entregar",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _etapas(caplog) -> dict[str, list[str]]:
    """Mensajes de etapa agrupados por id de cuento."""
    por_cuento: dict[str, list[str]] = {}
    for registro in caplog.records:
        m = re.fullmatch(r"cuento=(\S+) etapa=(\w+) ms=\d+", registro.getMessage())
        if m:
            por_cuento.setdefault(m.group(1), []).append(m.group(2))
    return por_cuento


def _entrar_invitado(entorno) -> dict[str, str]:
    r = entorno.cliente.post("/v1/invitado")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _crear_invitado(entorno, cab):
    return entorno.cliente.post(
        "/v1/invitado/cuentos",
        data={"edad": "8", "personaje": "un dragón"},
        files={"dibujo": ("d.png", dibujo_png(), "image/png")},
        headers=cab,
    )


# ------------------------------------------------------------------ log por etapa


def test_cuento_con_cuenta_registra_cada_etapa_sin_datos_del_nino(entorno, caplog):
    caplog.set_level(logging.INFO)
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab, apodo="Luna")
    cuento_id = entorno.crear_cuento(cab, perfil, personaje="un dragón").json()["id"]

    etapas = _etapas(caplog)[cuento_id]
    assert set(etapas) >= ETAPAS_CUENTO
    # Solo id, etapa y milisegundos: ni el personaje ni el apodo llegan al log de etapas
    mensajes = [r.getMessage() for r in caplog.records if "etapa=" in r.getMessage()]
    assert not any("dragón" in m or "Luna" in m for m in mensajes)


def test_cuento_de_invitado_registra_cada_etapa(crear_entorno, caplog):
    caplog.set_level(logging.INFO)
    entorno = crear_entorno(permitir_invitados=True)
    cab = _entrar_invitado(entorno)
    trabajo = _crear_invitado(entorno, cab).json()["id"]

    etapas = set(_etapas(caplog)[trabajo])
    assert ETAPAS_CUENTO | {"leer_almacen", "borrar_almacen"} <= etapas


# ------------------------------------------------------------------ tope por llamada


class ImagenColgada(ImagenFalsa):
    """Como una respuesta que nunca termina de llegar."""

    timeout_s = 0.2

    async def generar_fondo(self, descripcion):
        self.llamadas += 1
        await asyncio.sleep(30)
        raise AssertionError("el tope debió cortar la llamada")


def test_fondo_colgado_un_solo_reintento_y_se_degrada(crear_entorno):
    entorno = crear_entorno(reintentos_por_paso=2)
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    imagen = ImagenColgada()
    entorno.c.orquestador.imagen = imagen

    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo" and len(cuento["paginas"]) == 3
    assert cuento["avisos"] == ["sin_escenarios"]
    # 3 páginas x (intento + 1 reintento), aunque REINTENTOS_POR_PASO permita 2
    assert imagen.llamadas == 6


def test_un_error_que_no_es_tiempo_sigue_con_todos_los_reintentos(crear_entorno):
    entorno = crear_entorno(reintentos_por_paso=2)
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.imagen.fallar = True

    entorno.crear_cuento(cab, perfil)
    assert entorno.c.imagen.llamadas == 9  # 3 páginas x 3 intentos


# ------------------------------------------------------------------ tope del cuento


class TextoLento(TextoFalso):
    timeout_s = 30.0

    async def escribir_cuento(self, solicitud):
        await asyncio.sleep(5)
        return await super().escribir_cuento(solicitud)


def test_tope_del_cuento_con_cuenta_falla_limpio(crear_entorno):
    entorno = crear_entorno(tiempo_maximo_cuento_s=0.3)
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.orquestador.texto = TextoLento()

    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "fallido"
    assert cuento["avisos"] == ["tiempo_agotado"]
    assert cuento["paginas"] == []
    assert entorno.c.almacen.objetos == {}


def test_tope_del_cuento_de_invitado_falla_limpio(crear_entorno):
    entorno = crear_entorno(permitir_invitados=True, tiempo_maximo_cuento_s=0.3)
    entorno.c.orquestador.texto = TextoLento()
    cab = _entrar_invitado(entorno)
    trabajo = _crear_invitado(entorno, cab).json()["id"]

    r = entorno.cliente.get(f"/v1/invitado/cuentos/{trabajo}", headers=cab).json()
    assert r["estado"] == "fallido" and r["avisos"] == ["tiempo_agotado"]
    assert entorno.c.almacen.objetos == {}


def _settings(**cambios) -> Settings:
    datos = dict(
        jwt_secreto="s" * 48,
        proveedor_vision="falso",
        proveedor_texto="falso",
        proveedor_moderacion="falso",
        proveedor_imagen="falso",
        proveedor_correo="falso",
        almacen="memoria",
    )
    datos.update(cambios)
    return Settings(_env_file=None, **datos)


def test_tope_del_cuento_automatico():
    assert _tiempo_maximo_cuento(_settings()) == TIEMPO_MAXIMO_CUENTO_S
    # Ollama por CPU tarda minutos: sin tope automático
    assert _tiempo_maximo_cuento(_settings(proveedor_texto="ollama")) is None
    assert _tiempo_maximo_cuento(_settings(tiempo_maximo_cuento_s=90)) == 90
    assert _settings().cloudflare_timeout_s == 45


# ------------------------------------------------------------------ Cloudflare


def _cf(http: httpx.AsyncClient, timeout_s: float = 45) -> ClienteCloudflare:
    return ClienteCloudflare(http, "cuenta123", "token-de-prueba", timeout_s, 0.011, (1.0, 1.0))


class CuerpoAGoteo(httpx.AsyncByteStream):
    """Cabeceras al instante y el cuerpo, de a poco: lo que pasó con el tercer fondo."""

    async def __aiter__(self):
        yield b'{"success": true, "result": {"image": "'
        await asyncio.sleep(30)
        yield b'"}}'


@pytest.mark.anyio
async def test_cuerpo_a_goteo_lo_corta_el_tope_de_la_llamada(caplog):
    caplog.set_level(logging.INFO, logger="httpx")

    def manejar(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=CuerpoAGoteo())

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as http:
        imagen = ImagenCloudflare(_cf(http), "@cf/black-forest-labs/flux-1-schnell", 4, 4.8, 9.6)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(imagen.generar_fondo("a meadow"), timeout=0.3)
    # httpx anota «200 OK» al llegar las cabeceras, antes de leer el cuerpo: en el log de
    # la API esa línea no marca el fin de la llamada.
    assert any("200 OK" in r.getMessage() for r in caplog.records)


@pytest.mark.anyio
async def test_timeout_de_httpx_se_vuelve_timeouterror():
    def manejar(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sin respuesta", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as http:
        imagen = ImagenCloudflare(_cf(http), "m", 4, 4.8, 9.6)
        with pytest.raises(TimeoutError, match="no respondió a tiempo"):
            await imagen.generar_fondo("a meadow")
