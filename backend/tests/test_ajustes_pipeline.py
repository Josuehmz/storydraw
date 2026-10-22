"""Rasgos del dibujo en el cuento, capacidades apagadas que no se reintentan y cuentos de
exactamente 3 páginas."""

from __future__ import annotations

import json

import httpx
import pytest

from app.dominio.puertos import (
    AtributosDibujo,
    CuentoTexto,
    PaginaTexto,
    SolicitudCuento,
    Uso,
)
from app.infra.adaptadores.comun import mensaje_solicitud
from app.infra.adaptadores.proveedor_ollama import ClienteOllama, TextoOllama, VisionOllama


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _grabador(respuesta: httpx.Response | Exception):
    peticiones: list[httpx.Request] = []

    def manejar(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    return peticiones, httpx.AsyncClient(transport=httpx.MockTransport(manejar))


# ------------------------------------------------------------------ 3a · rasgos del dibujo


def test_el_cuento_recibe_los_rasgos_del_dibujo(entorno):
    """Con el personaje elegido («Dinosaurio»), el paso del cuento recibe además los
    colores, elementos y emoción que vio la visión, para no inventar otros."""
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil, personaje="Dinosaurio").json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo" and cuento["personaje"] == "Dinosaurio"
    solicitud = entorno.c.texto.solicitudes[-1]
    assert solicitud.personaje == "Dinosaurio" and solicitud.paginas == 3
    assert solicitud.atributos == AtributosDibujo(("verde",), ("cola larga", "alas"), "alegre")
    # La entrada que se modera incluye los rasgos que van al prompt
    assert "verde" in entorno.c.texto.textos_moderados[0]


def test_rasgos_con_terminos_bloqueados_no_llegan_al_cuento(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.vision.atributos = AtributosDibujo(("verde", "sangre"), ("pistola", "alas"), "")
    entorno.crear_cuento(cab, perfil, personaje="Dinosaurio")
    atributos = entorno.c.texto.solicitudes[-1].atributos
    assert atributos.colores == ("verde",) and atributos.elementos == ("alas",)


def test_prompt_del_cuento_con_y_sin_rasgos():
    con = mensaje_solicitud(
        SolicitudCuento("Dinosaurio", 7, 3, AtributosDibujo(("verde",), ("cola",), "alegre"))
    )
    assert "colores: verde" in con and "elementos: cola" in con and "emoción: alegre" in con
    assert "no inventes" in con and "Exactamente 3 páginas" in con
    sin = mensaje_solicitud(SolicitudCuento("Dinosaurio", 7))
    assert "no los describas ni los inventes" in sin


@pytest.mark.anyio
async def test_ollama_vision_lee_rasgos_y_el_cuento_los_envia():
    datos = {
        "hipotesis": [{"etiqueta": "Dinosaurio", "confianza": 0.9}],
        "atributos": {"colores": ["verde", "verde", ""], "elementos": ["cola"], "emocion": "feliz"},
    }
    respuesta = httpx.Response(200, json={"message": {"content": json.dumps(datos)}})
    peticiones, http = _grabador(respuesta)
    async with http:
        cliente = ClienteOllama(http, "http://localhost:11434", 60)
        res = await VisionOllama(cliente, "gemma3:4b").identificar(b"png")
    formato = json.loads(peticiones[0].content)["format"]
    assert "atributos" in formato["required"]
    assert res.atributos == AtributosDibujo(("verde",), ("cola",), "feliz")

    cuento = {"titulo": "t", "paginas": [{"texto": "x", "escena": "y"}] * 3}
    peticiones, http = _grabador(
        httpx.Response(200, json={"message": {"content": json.dumps(cuento)}})
    )
    async with http:
        cliente = ClienteOllama(http, "http://localhost:11434", 60)
        await TextoOllama(cliente, "gemma3:4b").escribir_cuento(
            SolicitudCuento("Dinosaurio", 7, 3, res.atributos)
        )
    sistema = json.loads(peticiones[0].content)["messages"][0]["content"]
    assert "colores: verde" in sistema


# ------------------------------------------------------------------ 3b · capacidad apagada


def _pasos(entorno, admin, cuento_id):
    filas = entorno.cliente.get("/v1/operacion/cuentos", headers=admin).json()
    return {p["paso"]: p for p in next(f for f in filas if f["id"] == cuento_id)["pasos"]}


def test_imagen_apagada_no_se_llama_ni_reintenta(crear_entorno):
    entorno = crear_entorno(proveedor_imagen="ninguno")
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo" and len(cuento["paginas"]) == 3
    assert cuento["avisos"] == ["sin_escenarios"]
    pasos = _pasos(entorno, admin, cuento_id)
    assert pasos["escenarios"]["estado"] == "omitido" and pasos["escenarios"]["intentos"] == 0
    assert pasos["escenarios"]["proveedor"] == "ninguno"


# ------------------------------------------------------------------ 3c · exactamente 3 páginas


def _cuento(paginas: int) -> CuentoTexto:
    return CuentoTexto(
        "La aventura",
        [PaginaTexto(f"Página {i} del cuento.", "meadow") for i in range(paginas)],
        Uso(100, 100),
    )


def test_cuento_incompleto_se_regenera_como_reintento(entorno):
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.cuentos_forzados = [_cuento(2), _cuento(3)]
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo" and len(cuento["paginas"]) == 3
    pasos = _pasos(entorno, admin, cuento_id)
    assert pasos["escribir"]["intentos"] == 2  # el incompleto contó como intento
    # El incompleto no llegó a la moderación del cuento: solo entrada + cuento completo
    assert len(entorno.c.texto.textos_moderados) == 2


def test_cuento_siempre_incompleto_no_se_entrega(entorno):
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.cuentos_forzados = [_cuento(2), _cuento(1)]  # 1 intento + 1 reintento
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "fallido" and cuento["paginas"] == []
    assert entorno.c.almacen.objetos == {}
    pasos = _pasos(entorno, admin, cuento_id)
    assert pasos["escribir"]["estado"] == "fallido" and pasos["escribir"]["intentos"] == 2
