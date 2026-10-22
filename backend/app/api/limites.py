"""Límite de tasa con slowapi: por IP y por cuenta.

Los límites concretos vienen de la configuración (`LIMITE_*`). El almacén del contador es
memoria por defecto; con varias réplicas se apunta a Redis con `LIMITE_TASA_ALMACEN`.
"""

from __future__ import annotations

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

_limites: dict[str, str] = {
    "auth": "10/minute",
    "identificar": "10/minute",
    "cuentos_ip": "5/minute",
    "cuentos_cuenta": "30/day",
}


def clave_ip(request: Request) -> str:
    return "ip:" + (get_remote_address(request) or "desconocida")


def clave_cuenta(request: Request) -> str:
    # `tutor_actual` deja el id en request.state antes de que se evalúe el límite.
    tutor_id = getattr(request.state, "tutor_id", None)
    return f"cuenta:{tutor_id}" if tutor_id else clave_ip(request)


limiter = Limiter(
    key_func=clave_ip,
    # Única lectura directa del entorno: el limitador se crea al importar el módulo.
    storage_uri=os.environ.get("LIMITE_TASA_ALMACEN", "memory://"),
)


def configurar(auth: str, identificar: str, cuentos_ip: str, cuentos_cuenta: str) -> None:
    _limites.update(
        auth=auth, identificar=identificar, cuentos_ip=cuentos_ip, cuentos_cuenta=cuentos_cuenta
    )
    limiter.reset()


def limite_auth() -> str:
    return _limites["auth"]


def limite_identificar() -> str:
    return _limites["identificar"]


def limite_cuentos_ip() -> str:
    return _limites["cuentos_ip"]


def limite_cuentos_cuenta() -> str:
    return _limites["cuentos_cuenta"]
