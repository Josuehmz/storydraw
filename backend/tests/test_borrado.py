"""Borrado a petición: cuento, perfil del niño y cuenta completa."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.dominio.puertos import CuentoTexto, PaginaTexto, Uso
from app.infra.orm import Consentimiento, Cuento, Pagina, Perfil, RegistroModeracion, Tutor
from tests.conftest import CONTRASENA


def _contar(entorno, modelo, *condiciones) -> int:
    async def _q():
        async with entorno.c.fabrica() as s:
            consulta = select(func.count()).select_from(modelo)
            for cond in condiciones:
                consulta = consulta.where(cond)
            return await s.scalar(consulta)

    return asyncio.run(_q())


def test_borrar_un_cuento(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    uno = entorno.crear_cuento(cab, perfil).json()["id"]
    dos = entorno.crear_cuento(cab, perfil).json()["id"]

    r = entorno.cliente.delete(f"/v1/cuentos/{uno}", headers=cab)
    assert r.status_code == 204
    assert entorno.cliente.get(f"/v1/cuentos/{uno}", headers=cab).status_code == 404
    assert not any(k.startswith(f"cuentos/{uno}/") for k in entorno.c.almacen.objetos)
    assert any(k.startswith(f"cuentos/{dos}/") for k in entorno.c.almacen.objetos)
    assert _contar(entorno, Pagina) == 3
    biblioteca = entorno.cliente.get(f"/v1/perfiles/{perfil}/cuentos", headers=cab).json()
    assert [c["id"] for c in biblioteca] == [dos]


def test_borrar_cuento_anonimiza_el_registro_de_moderacion(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    malo = CuentoTexto("violencia", [PaginaTexto("violencia", "x")] * 3, Uso())
    entorno.c.texto.cuentos_forzados = [malo]
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    assert _contar(entorno, RegistroModeracion, RegistroModeracion.texto.is_not(None)) == 1

    assert entorno.cliente.delete(f"/v1/cuentos/{cuento_id}", headers=cab).status_code == 204
    assert _contar(entorno, RegistroModeracion) == 1  # se conserva la estadística
    assert _contar(entorno, RegistroModeracion, RegistroModeracion.texto.is_not(None)) == 0


def test_no_se_borra_lo_ajeno(entorno):
    cab = entorno.registrar("a@correo.com")
    otro = entorno.registrar("b@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    assert entorno.cliente.delete(f"/v1/cuentos/{cuento_id}", headers=otro).status_code == 404
    assert entorno.cliente.delete(f"/v1/perfiles/{perfil}", headers=otro).status_code == 404
    assert _contar(entorno, Cuento) == 1


def test_borrar_perfil_borra_sus_cuentos(entorno):
    cab = entorno.registrar("a@correo.com")
    luna = entorno.crear_perfil(cab, "Luna", 8)
    sol = entorno.crear_perfil(cab, "Sol", 10)
    entorno.crear_cuento(cab, luna)
    otro = entorno.crear_cuento(cab, sol).json()["id"]

    assert entorno.cliente.delete(f"/v1/perfiles/{luna}", headers=cab).status_code == 204
    assert _contar(entorno, Perfil) == 1
    assert _contar(entorno, Cuento) == 1
    assert all(k.startswith(f"cuentos/{otro}/") for k in entorno.c.almacen.objetos)


def test_borrar_cuenta_completa(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.crear_cuento(cab, perfil)

    assert entorno.cliente.delete("/v1/auth/cuenta", headers=cab).status_code == 204
    for modelo in (Tutor, Consentimiento, Perfil, Cuento, Pagina):
        assert _contar(entorno, modelo) == 0, modelo.__name__
    assert entorno.c.almacen.objetos == {}
    r = entorno.cliente.post(
        "/v1/auth/login", json={"email": "a@correo.com", "contrasena": CONTRASENA}
    )
    assert r.status_code == 401
