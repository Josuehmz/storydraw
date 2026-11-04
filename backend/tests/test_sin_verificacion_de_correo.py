"""Cuentas sin correo de verificación (VERIFICAR_CORREO=false), para un piloto sin SMTP.

Con la verificación apagada, la cuenta nace confirmada y se entra al momento; el
consentimiento sigue siendo obligatorio. Con la verificación encendida (por defecto) todo
sigue igual: lo cubren test_auth.py y test_verificacion_correo.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.conftest import CONTRASENA


def _registro(entorno, email: str, consiente: bool = True):
    return entorno.cliente.post(
        "/v1/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "acepta_consentimiento": consiente},
    )


def _login(entorno, email: str, contrasena: str = CONTRASENA):
    return entorno.cliente.post("/v1/auth/login", json={"email": email, "contrasena": contrasena})


@pytest.fixture
def sin_correo(crear_entorno):
    return crear_entorno(proveedor_correo="ninguno", verificar_correo=False)


def test_sin_verificacion_la_cuenta_nace_confirmada_y_se_entra_al_momento(sin_correo):
    r = _registro(sin_correo, "ana@correo.com")
    assert r.status_code == 201, r.text
    assert r.json()["verificado"] is True
    assert r.json()["correo_enviado"] is False

    r = _login(sin_correo, "ana@correo.com")
    assert r.status_code == 200, r.text
    cab = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (
        sin_correo.cliente.post(
            "/v1/perfiles", json={"apodo": "Luna", "edad": 8}, headers=cab
        ).status_code
        == 201
    )


def test_sin_verificacion_el_consentimiento_y_la_contrasena_siguen_mandando(sin_correo):
    assert _registro(sin_correo, "ana@correo.com", consiente=False).status_code == 422
    _registro(sin_correo, "luis@correo.com")
    assert _login(sin_correo, "luis@correo.com", "otra-clave-larga-999").status_code == 401
    assert _registro(sin_correo, "luis@correo.com").status_code == 409


def test_sin_verificacion_reenviar_no_hace_nada(sin_correo):
    _registro(sin_correo, "ana@correo.com")
    r = sin_correo.cliente.post(
        "/v1/auth/reenviar-verificacion",
        json={"email": "ana@correo.com", "contrasena": CONTRASENA},
    )
    assert r.status_code == 202 and r.json() == {"enviado": False}


def test_sin_verificacion_con_el_correo_falso_no_se_manda_nada(crear_entorno):
    entorno = crear_entorno(verificar_correo=False)  # correo falso de las pruebas
    _registro(entorno, "ana@correo.com")
    assert entorno.c.correo.enviados == []
    assert _login(entorno, "ana@correo.com").status_code == 200


def test_la_salud_dice_que_el_correo_esta_apagado(sin_correo):
    assert sin_correo.cliente.get("/salud").json()["proveedores"]["correo"] == "ninguno"


def test_con_verificacion_por_defecto_sin_confirmar_no_se_entra(entorno):
    _registro(entorno, "ana@correo.com")
    assert _login(entorno, "ana@correo.com").status_code == 403


def _base(**cambios) -> dict:
    datos = dict(
        jwt_secreto="s" * 48,
        **{f"proveedor_{c}": "falso" for c in ("vision", "texto", "moderacion", "imagen")},
        almacen="memoria",
    )
    datos.update(cambios)
    return datos


def test_sin_correo_hay_que_apagar_la_verificacion():
    with pytest.raises(ValidationError, match="VERIFICAR_CORREO=false"):
        Settings(_env_file=None, **_base(proveedor_correo="ninguno"))
    s = Settings(_env_file=None, **_base(proveedor_correo="ninguno", verificar_correo=False))
    assert s.verificar_correo is False


def test_produccion_admite_el_correo_apagado_sin_smtp():
    s = Settings(
        _env_file=None,
        entorno="produccion",
        jwt_secreto="s" * 48,
        proveedor_vision="cloudflare",
        proveedor_texto="cloudflare",
        proveedor_imagen="cloudflare",
        proveedor_moderacion="openai",
        openai_api_key="clave-de-prueba",
        cloudflare_account_id="cuenta",
        cloudflare_api_token="token-de-prueba",
        proveedor_correo="ninguno",
        verificar_correo=False,
        s3_access_key="acceso",
        s3_secret_key="secreto",
    )
    assert (s.proveedor_correo, s.smtp_host) == ("ninguno", "")
