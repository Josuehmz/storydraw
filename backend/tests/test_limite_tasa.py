"""Límite de tasa con slowapi, por IP y por cuenta."""

from __future__ import annotations

from tests.conftest import CONTRASENA


def test_limite_por_ip_al_crear_cuentos(crear_entorno):
    entorno = crear_entorno(limite_cuentos_ip="2/minute")
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    estados = [entorno.crear_cuento(cab, perfil).status_code for _ in range(3)]
    assert estados == [202, 202, 429]


def test_limite_por_cuenta_no_afecta_a_otra_cuenta(crear_entorno):
    entorno = crear_entorno(limite_cuentos_cuenta="1/minute")
    a = entorno.registrar("a@correo.com")
    b = entorno.registrar("b@correo.com")
    perfil_a = entorno.crear_perfil(a)
    perfil_b = entorno.crear_perfil(b)
    assert entorno.crear_cuento(a, perfil_a).status_code == 202
    assert entorno.crear_cuento(a, perfil_a).status_code == 429
    # Misma IP, otra cuenta: su propio cupo.
    assert entorno.crear_cuento(b, perfil_b).status_code == 202


def test_limite_en_login(crear_entorno):
    entorno = crear_entorno(limite_auth="3/minute")
    datos = {"email": "nadie@correo.com", "contrasena": CONTRASENA}
    estados = [entorno.cliente.post("/v1/auth/login", json=datos).status_code for _ in range(4)]
    assert estados == [401, 401, 401, 429]


def test_limite_en_identificar(crear_entorno):
    from tests.conftest import dibujo_png

    entorno = crear_entorno(limite_identificar="1/minute", limite_auth="100/minute")
    cab = entorno.registrar("a@correo.com")
    archivos = {"dibujo": ("d.png", dibujo_png(), "image/png")}
    assert (
        entorno.cliente.post("/v1/dibujos/identificar", files=archivos, headers=cab).status_code
        == 200
    )
    archivos = {"dibujo": ("d.png", dibujo_png(), "image/png")}
    assert (
        entorno.cliente.post("/v1/dibujos/identificar", files=archivos, headers=cab).status_code
        == 429
    )
