"""Registro con consentimiento previo, verificación por correo y login JWT."""

from __future__ import annotations

import asyncio

import jwt
from sqlalchemy import func, select

from app.infra.orm import Consentimiento, Perfil, Tutor
from tests.conftest import CONTRASENA


def _contar(entorno, modelo) -> int:
    async def _q():
        async with entorno.c.fabrica() as s:
            return await s.scalar(select(func.count()).select_from(modelo))

    return asyncio.run(_q())


def test_registro_sin_consentimiento_no_escribe_nada(entorno):
    r = entorno.cliente.post(
        "/v1/auth/registro",
        json={
            "email": "tutor@correo.com",
            "contrasena": CONTRASENA,
            "acepta_consentimiento": False,
        },
    )
    assert r.status_code == 422
    assert _contar(entorno, Tutor) == 0
    assert entorno.c.correo.enviados == []


def test_registro_guarda_consentimiento_y_envia_verificacion(entorno):
    r = entorno.cliente.post(
        "/v1/auth/registro",
        json={"email": "Tutor@CORREO.com", "contrasena": CONTRASENA, "acepta_consentimiento": True},
    )
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["verificado"] is False
    assert cuerpo["email"] == "tutor@correo.com"
    assert _contar(entorno, Consentimiento) == 1
    para, _asunto, texto = entorno.c.correo.enviados[0]
    assert para == "tutor@correo.com" and "/v1/auth/verificar?token=" in texto

    duplicado = entorno.cliente.post(
        "/v1/auth/registro",
        json={"email": "tutor@correo.com", "contrasena": CONTRASENA, "acepta_consentimiento": True},
    )
    assert duplicado.status_code == 409


def test_contrasena_con_argon2id(entorno):
    entorno.registrar("hash@correo.com", verificar=False)

    async def _hash():
        async with entorno.c.fabrica() as s:
            return await s.scalar(select(Tutor.hash_contrasena))

    guardado = asyncio.run(_hash())
    assert guardado.startswith("$argon2id$")
    assert CONTRASENA not in guardado


def test_login_exige_correo_verificado(entorno):
    entorno.registrar("lento@correo.com", verificar=False)
    r = entorno.cliente.post(
        "/v1/auth/login", json={"email": "lento@correo.com", "contrasena": CONTRASENA}
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "correo_sin_verificar"


def test_login_jwt_y_acceso_a_perfiles(entorno):
    cabeceras = entorno.registrar("ok@correo.com")
    token = cabeceras["Authorization"].split()[1]
    carga = jwt.decode(token, options={"verify_signature": False})
    assert carga["tipo"] == "acceso" and carga["rol"] == "tutor"

    assert entorno.cliente.get("/v1/perfiles", headers=cabeceras).json() == []
    perfil_id = entorno.crear_perfil(cabeceras, "Sol", 7)
    lista = entorno.cliente.get("/v1/perfiles", headers=cabeceras).json()
    assert [p["id"] for p in lista] == [perfil_id]


def test_credenciales_y_tokens_invalidos(entorno):
    entorno.registrar("x@correo.com")
    malo = entorno.cliente.post(
        "/v1/auth/login", json={"email": "x@correo.com", "contrasena": "nope"}
    )
    assert malo.status_code == 401
    assert entorno.cliente.get("/v1/perfiles").status_code == 401
    falso = {"Authorization": "Bearer no-es-un-jwt"}
    assert entorno.cliente.get("/v1/perfiles", headers=falso).status_code == 401
    # Un token de verificación no sirve como token de acceso.
    tutor_token = entorno.c.correo.enviados[-1][2].split("token=")[1].strip()
    cab = {"Authorization": f"Bearer {tutor_token}"}
    assert entorno.cliente.get("/v1/perfiles", headers=cab).status_code == 401


def test_rango_de_edad_6_a_12(entorno):
    cabeceras = entorno.registrar("edad@correo.com")
    for edad in (5, 13):
        r = entorno.cliente.post(
            "/v1/perfiles", json={"apodo": "Mia", "edad": edad}, headers=cabeceras
        )
        assert r.status_code == 422
    assert _contar(entorno, Perfil) == 0
    entorno.crear_perfil(cabeceras, "Mia", 6)
    entorno.crear_perfil(cabeceras, "Leo", 12)


def test_sin_verificar_no_se_crea_perfil(entorno):
    """Sin correo verificado no hay token de acceso, y sin token no se escribe ningún perfil."""
    entorno.registrar("nov@correo.com", verificar=False)
    r = entorno.cliente.post("/v1/perfiles", json={"apodo": "Ana", "edad": 8})
    assert r.status_code == 401
    assert _contar(entorno, Perfil) == 0


def test_rol_admin_por_configuracion(entorno):
    cabeceras = entorno.registrar("admin@storydraw.com")
    assert entorno.cliente.get("/v1/operacion/resumen", headers=cabeceras).status_code == 200
    normal = entorno.registrar("papa@correo.com")
    assert entorno.cliente.get("/v1/operacion/resumen", headers=normal).status_code == 403
