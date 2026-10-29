"""Dominios permitidos, correo de confirmación y la página que devuelve al niño a la app."""

from __future__ import annotations

import re
import smtplib
from email import message_from_bytes, policy
from typing import ClassVar

import pytest

from app.api.plantillas import pagina_confirmada
from app.config import Settings
from app.infra.adaptadores.correo_smtp import CorreoSMTP
from tests.conftest import CONTRASENA

HTML = {"accept": "text/html,application/xhtml+xml"}


def _registro(entorno, email: str):
    return entorno.cliente.post(
        "/v1/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "acepta_consentimiento": True},
    )


def _token(entorno) -> str:
    return re.search(r"token=([\w\-\.]+)", entorno.c.correo.enviados[-1][2]).group(1)


# ------------------------------------------------------------------ dominios


def test_por_defecto_solo_gmail_y_hotmail():
    s = Settings(
        _env_file=None,
        jwt_secreto="s" * 48,
        proveedor_vision="falso",
        proveedor_texto="falso",
        proveedor_moderacion="falso",
        proveedor_imagen="falso",
        proveedor_correo="falso",
        almacen="memoria",
    )
    assert s.lista_dominios_correo == ["gmail.com", "hotmail.com"]


@pytest.mark.parametrize("email", ["ana@gmail.com", "Ana@GMAIL.com", "luis@hotmail.com"])
def test_gmail_y_hotmail_pueden_registrarse(crear_entorno, email):
    entorno = crear_entorno(dominios_correo="gmail.com,hotmail.com")
    r = _registro(entorno, email)
    assert r.status_code == 201, r.text
    assert len(entorno.c.correo.enviados) == 1


@pytest.mark.parametrize(
    "email",
    [
        "ana@yahoo.com",
        "ana@outlook.com",
        "ana@correo.com",
        "ana@gmail.com.evil.com",  # el dominio entero debe coincidir
        "ana@evilgmail.com",
        "ana@mail.hotmail.com",
    ],
)
def test_otros_dominios_se_rechazan_sin_crear_cuenta_ni_enviar_correo(crear_entorno, email):
    entorno = crear_entorno(dominios_correo="gmail.com,hotmail.com")
    r = _registro(entorno, email)
    assert r.status_code == 422 and r.json()["detail"] == "dominio_no_permitido"
    assert entorno.c.correo.enviados == []
    # Sin cuenta, tampoco hay forma de iniciar sesión con ese correo
    login = entorno.cliente.post("/v1/auth/login", json={"email": email, "contrasena": CONTRASENA})
    assert login.status_code == 401


def test_el_dominio_es_configurable_y_vacio_permite_todos(crear_entorno):
    abierto = crear_entorno(dominios_correo="")
    assert _registro(abierto, "ana@cualquiera.org").status_code == 201
    solo_hotmail = crear_entorno(dominios_correo="hotmail.com")
    assert _registro(solo_hotmail, "ana@gmail.com").status_code == 422


# ------------------------------------------------------------------ correo


def test_el_correo_trae_texto_y_html_con_el_mismo_enlace(entorno):
    assert _registro(entorno, "ana@gmail.com").status_code == 201
    para, asunto, texto = entorno.c.correo.enviados[0]
    html = entorno.c.correo.html[0]
    assert para == "ana@gmail.com" and asunto == "Confirma tu correo en StoryDraw"
    enlace = re.search(r"(http\S+/v1/auth/verificar\?token=[\w\-\.]+)", texto).group(1)
    assert "Confirmar mi correo" in html and enlace in html
    assert enlace.startswith(entorno.c.settings.url_publica)


# ------------------------------------------------------------------ al tocar el enlace


def test_el_navegador_recibe_una_pagina_que_abre_la_app(entorno):
    _registro(entorno, "ana@gmail.com")
    r = entorno.cliente.get("/v1/auth/verificar", params={"token": _token(entorno)}, headers=HTML)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Correo confirmado" in r.text and "Abrir StoryDraw" in r.text
    # El correo viaja en el enlace para prellenar el inicio de sesión
    assert "storydraw://verificado?email=ana%40gmail.com" in r.text
    assert "intent://verificado?email=ana%40gmail.com" in r.text
    assert "package=com.storydraw.storydraw" in r.text


def test_confirmar_deja_iniciar_sesion_y_el_enlace_se_puede_tocar_dos_veces(entorno):
    _registro(entorno, "ana@gmail.com")
    antes = entorno.cliente.post(
        "/v1/auth/login", json={"email": "ana@gmail.com", "contrasena": CONTRASENA}
    )
    assert antes.status_code == 403 and antes.json()["detail"] == "correo_sin_verificar"

    token = _token(entorno)
    for _ in range(2):  # los antivirus y los clientes de correo a veces abren el enlace antes
        r = entorno.cliente.get("/v1/auth/verificar", params={"token": token}, headers=HTML)
        assert r.status_code == 200

    despues = entorno.cliente.post(
        "/v1/auth/login", json={"email": "ana@gmail.com", "contrasena": CONTRASENA}
    )
    assert despues.status_code == 200 and despues.json()["access_token"]


def test_una_api_sin_navegador_sigue_recibiendo_json(entorno):
    _registro(entorno, "ana@gmail.com")
    r = entorno.cliente.get("/v1/auth/verificar", params={"token": _token(entorno)})
    assert r.status_code == 200 and r.json() == {"verificado": True}


def test_enlace_invalido_muestra_una_pagina_que_explica_como_reenviar(entorno):
    r = entorno.cliente.get("/v1/auth/verificar", params={"token": "basura"}, headers=HTML)
    assert r.status_code == 400 and "Reenviar correo" in r.text
    assert "storydraw://" not in r.text
    api = entorno.cliente.get("/v1/auth/verificar", params={"token": "basura"})
    assert api.status_code == 400 and api.json()["detail"] == "token_invalido"


def test_la_pagina_escapa_el_correo():
    pagina = pagina_confirmada('a"<script>@x.com', 'storydraw://v?e="x', 'intent://v?e="x')
    assert "<script>@x.com" not in pagina
    assert '"x' not in pagina.split("<script>")[0]  # ni en atributos ni en el texto


# ------------------------------------------------------------------ si el correo no sale


def test_si_el_correo_falla_la_cuenta_queda_y_se_puede_reenviar(entorno):
    entorno.c.correo.fallar = True
    r = _registro(entorno, "ana@gmail.com")
    assert r.status_code == 201 and r.json()["correo_enviado"] is False
    assert entorno.c.correo.enviados == []

    entorno.c.correo.fallar = False
    re_enviado = entorno.cliente.post(
        "/v1/auth/reenviar-verificacion",
        json={"email": "ana@gmail.com", "contrasena": CONTRASENA},
    )
    assert re_enviado.status_code == 202 and len(entorno.c.correo.enviados) == 1

    ok = entorno.cliente.get("/v1/auth/verificar", params={"token": _token(entorno)}, headers=HTML)
    assert ok.status_code == 200
    login = entorno.cliente.post(
        "/v1/auth/login", json={"email": "ana@gmail.com", "contrasena": CONTRASENA}
    )
    assert login.status_code == 200


def test_reenviar_con_contrasena_equivocada_no_envia_nada(entorno):
    _registro(entorno, "ana@gmail.com")
    enviados = len(entorno.c.correo.enviados)
    r = entorno.cliente.post(
        "/v1/auth/reenviar-verificacion",
        json={"email": "ana@gmail.com", "contrasena": "nope-nope-1"},
    )
    assert r.status_code == 202 and len(entorno.c.correo.enviados) == enviados


# ------------------------------------------------------------------ adaptador SMTP


class _SMTPFalso:
    instancias: ClassVar[list[_SMTPFalso]] = []

    def __init__(self, host, puerto, timeout=None, context=None):
        self.args = (host, puerto)
        self.pasos: list[str] = []
        self.mensaje = None
        _SMTPFalso.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, context=None):
        self.pasos.append("starttls")

    def login(self, usuario, contrasena):
        self.pasos.append(f"login:{usuario}:{contrasena}")

    def send_message(self, mensaje):
        self.mensaje = mensaje
        self.pasos.append("enviar")


@pytest.mark.anyio
async def test_smtp_manda_texto_y_html_con_starttls_y_login(monkeypatch):
    _SMTPFalso.instancias.clear()
    monkeypatch.setattr(smtplib, "SMTP", _SMTPFalso)
    correo = CorreoSMTP(
        "smtp.gmail.com",
        587,
        "yo@gmail.com",
        "clave-de-app",
        "StoryDraw <yo@gmail.com>",
        "starttls",
    )
    await correo.enviar(
        "ana@hotmail.com", "Asunto con tilde: confirmación", "texto plano", "<b>hola</b>"
    )

    servidor = _SMTPFalso.instancias[0]
    assert servidor.args == ("smtp.gmail.com", 587)
    assert servidor.pasos == ["starttls", "login:yo@gmail.com:clave-de-app", "enviar"]
    # Se serializa y se vuelve a leer: así llega a la bandeja de entrada
    recibido = message_from_bytes(servidor.mensaje.as_bytes(), policy=policy.default)
    assert recibido["To"] == "ana@hotmail.com" and recibido["From"] == "StoryDraw <yo@gmail.com>"
    assert recibido["Subject"] == "Asunto con tilde: confirmación"
    assert recibido.get_body(("plain",)).get_content().strip() == "texto plano"
    assert recibido.get_body(("html",)).get_content().strip() == "<b>hola</b>"


@pytest.fixture
def anyio_backend():
    return "asyncio"
