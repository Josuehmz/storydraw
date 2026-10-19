"""Perfiles por niño y su biblioteca."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencias import contenedor, repositorio, tutor_con_consentimiento
from app.api.esquemas import CuentoResumen, PerfilEntrada, PerfilSalida
from app.contenedor import Contenedor
from app.infra.orm import Tutor
from app.infra.repositorio import Repositorio
from app.servicios import a_resumen, borrar_cuentos

router = APIRouter(prefix="/v1/perfiles", tags=["perfiles y biblioteca"])


@router.get("", response_model=list[PerfilSalida])
async def listar(
    tutor: Tutor = Depends(tutor_con_consentimiento), repo: Repositorio = Depends(repositorio)
) -> list:
    return await repo.perfiles_de(tutor.id)


@router.post("", response_model=PerfilSalida, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: PerfilEntrada,
    tutor: Tutor = Depends(tutor_con_consentimiento),
    repo: Repositorio = Depends(repositorio),
):
    return await repo.crear_perfil(tutor.id, datos.apodo.strip(), datos.edad)


@router.delete("/{perfil_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar(
    perfil_id: uuid.UUID,
    tutor: Tutor = Depends(tutor_con_consentimiento),
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> Response:
    if await repo.perfil_de(tutor.id, perfil_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "perfil_inexistente")
    await borrar_cuentos(c, await repo.ids_cuentos(perfil_id=perfil_id))
    await repo.borrar_perfil(perfil_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{perfil_id}/cuentos", response_model=list[CuentoResumen])
async def biblioteca(
    perfil_id: uuid.UUID,
    tutor: Tutor = Depends(tutor_con_consentimiento),
    repo: Repositorio = Depends(repositorio),
) -> list[CuentoResumen]:
    if await repo.perfil_de(tutor.id, perfil_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "perfil_inexistente")
    return [a_resumen(c) for c in await repo.cuentos_de_perfil(perfil_id)]
