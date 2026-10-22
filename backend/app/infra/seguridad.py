"""Contraseñas con Argon2id y tokens JWT con PyJWT."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

TipoToken = Literal["acceso", "verificacion"]
_ALGORITMO = "HS256"


class TokenInvalido(Exception):
    pass


class Hasher:
    """argon2-cffi usa Argon2id por defecto (RFC 9106)."""

    def __init__(self) -> None:
        self._ph = PasswordHasher()

    def hashear(self, contrasena: str) -> str:
        return self._ph.hash(contrasena)

    def verificar(self, hash_guardado: str, contrasena: str) -> bool:
        try:
            return self._ph.verify(hash_guardado, contrasena)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


class Tokens:
    def __init__(self, secreto: str, minutos_acceso: int, horas_verificacion: int):
        self._secreto = secreto
        self._minutos = minutos_acceso
        self._horas = horas_verificacion

    def emitir(self, sujeto: uuid.UUID, tipo: TipoToken, rol: str = "tutor") -> tuple[str, int]:
        duracion = (
            timedelta(minutes=self._minutos) if tipo == "acceso" else timedelta(hours=self._horas)
        )
        ahora = datetime.now(UTC)
        carga = {
            "sub": str(sujeto),
            "tipo": tipo,
            "rol": rol,
            "iat": ahora,
            "exp": ahora + duracion,
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(carga, self._secreto, algorithm=_ALGORITMO), int(duracion.total_seconds())

    def leer(self, token: str, tipo: TipoToken) -> dict:
        try:
            carga = jwt.decode(
                token,
                self._secreto,
                algorithms=[_ALGORITMO],
                options={"require": ["exp", "sub", "tipo"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenInvalido(str(exc)) from exc
        if carga.get("tipo") != tipo:
            raise TokenInvalido("tipo de token incorrecto")
        return carga
