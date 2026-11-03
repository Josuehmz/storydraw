"""Adaptador de correo: SMTP transaccional (STARTTLS, TLS directo o sin cifrar en local)."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from typing import Literal

from app.dominio.puertos import ICorreo


class CorreoSMTP(ICorreo):
    proveedor = "smtp"

    def __init__(
        self,
        host: str,
        puerto: int,
        usuario: str,
        contrasena: str,
        remitente: str,
        seguridad: Literal["starttls", "ssl", "ninguna"],
        timeout_s: float = 20.0,
    ):
        self._host = host
        self._puerto = puerto
        self._usuario = usuario
        self._contrasena = contrasena
        self._remitente = remitente
        self._seguridad = seguridad
        self._timeout = timeout_s

    def _enviar(self, mensaje: EmailMessage) -> None:
        contexto = ssl.create_default_context()
        if self._seguridad == "ssl":
            servidor: smtplib.SMTP = smtplib.SMTP_SSL(
                self._host, self._puerto, timeout=self._timeout, context=contexto
            )
        else:
            servidor = smtplib.SMTP(self._host, self._puerto, timeout=self._timeout)
        with servidor:
            if self._seguridad == "starttls":
                servidor.starttls(context=contexto)
            if self._usuario:
                servidor.login(self._usuario, self._contrasena)
            servidor.send_message(mensaje)

    async def enviar(self, para: str, asunto: str, cuerpo: str, html: str | None = None) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self._remitente
        mensaje["To"] = para
        mensaje["Subject"] = asunto
        mensaje.set_content(cuerpo)
        if html:
            mensaje.add_alternative(html, subtype="html")
        await asyncio.to_thread(self._enviar, mensaje)
