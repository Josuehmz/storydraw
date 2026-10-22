"""Dependencias comunes: contenedor, sesión de BD y usuario autenticado."""

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.contenedor import Contenedor
from app.infra.orm import Tutor
from app.infra.repositorio import Repositorio
from app.infra.seguridad import TokenInvalido

_bearer = HTTPBearer(auto_error=False)


def contenedor(request: Request) -> Contenedor:
    return request.app.state.contenedor


async def sesion(c: Contenedor = Depends(contenedor)) -> AsyncIterator[AsyncSession]:
    async with c.fabrica() as s:
        yield s


async def repositorio(s: AsyncSession = Depends(sesion)) -> Repositorio:
    return Repositorio(s)


async def tutor_actual(
    request: Request,
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> Tutor:
    no_autorizado = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "no_autenticado", headers={"WWW-Authenticate": "Bearer"}
    )
    if credenciales is None:
        raise no_autorizado
    try:
        carga = c.tokens.leer(credenciales.credentials, "acceso")
        tutor_id = uuid.UUID(carga["sub"])
    except (TokenInvalido, ValueError) as exc:
        raise no_autorizado from exc
    tutor = await repo.tutor_por_id(tutor_id)
    if tutor is None:
        raise no_autorizado
    if not tutor.verificado:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "correo_sin_verificar")
    request.state.tutor_id = str(tutor.id)
    return tutor


async def tutor_con_consentimiento(
    tutor: Tutor = Depends(tutor_actual), repo: Repositorio = Depends(repositorio)
) -> Tutor:
    """Ningún dato del niño se escribe ni se procesa sin consentimiento registrado."""
    if not await repo.tiene_consentimiento(tutor.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "sin_consentimiento")
    return tutor


def requiere_rol(*roles: str):
    async def _verificar(tutor: Tutor = Depends(tutor_actual)) -> Tutor:
        if tutor.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "sin_permiso")
        return tutor

    return _verificar
