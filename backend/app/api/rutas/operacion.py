"""Panel de operación: latencia y costo por cuento, y cola de revisión de moderación."""

import statistics
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencias import repositorio, requiere_rol
from app.api.esquemas import (
    CuentoMetrica,
    PasoMetrica,
    RegistroModeracionSalida,
    ResumenOperacion,
)
from app.infra.repositorio import Repositorio

router = APIRouter(prefix="/v1/operacion", tags=["operación"])

solo_admin = requiere_rol("admin")
admin_o_contenido = requiere_rol("admin", "contenido")


@router.get("/cuentos", response_model=list[CuentoMetrica], dependencies=[Depends(solo_admin)])
async def cuentos(
    limite: int = Query(50, ge=1, le=500), repo: Repositorio = Depends(repositorio)
) -> list[CuentoMetrica]:
    return [
        CuentoMetrica(
            id=c.id,
            estado=c.estado,
            latencia_ms=c.latencia_ms,
            costo_usd=c.costo_usd,
            avisos=list(c.avisos or []),
            pasos=[PasoMetrica(**p) for p in (c.pasos or [])],
            creado_en=c.creado_en,
        )
        for c in await repo.cuentos_recientes(limite)
    ]


@router.get("/resumen", response_model=ResumenOperacion, dependencies=[Depends(solo_admin)])
async def resumen(
    dias: int = Query(30, ge=1, le=365), repo: Repositorio = Depends(repositorio)
) -> ResumenOperacion:
    lista = await repo.cuentos_desde(datetime.now(UTC) - timedelta(days=dias))
    latencias = sorted(c.latencia_ms for c in lista if c.latencia_ms is not None)
    costos = [c.costo_usd for c in lista if c.costo_usd is not None]
    p95 = None
    if latencias:
        p95 = float(latencias[min(len(latencias) - 1, round(0.95 * (len(latencias) - 1)))])
    degradaciones = Counter(a for c in lista for a in (c.avisos or []))
    return ResumenOperacion(
        cuentos=len(lista),
        por_estado=dict(Counter(c.estado for c in lista)),
        latencia_media_ms=statistics.fmean(latencias) if latencias else None,
        latencia_p95_ms=p95,
        costo_medio_usd=round(statistics.fmean(costos), 6) if costos else None,
        costo_total_usd=round(sum(costos), 6),
        degradaciones=dict(degradaciones),
    )


@router.get(
    "/moderacion",
    response_model=list[RegistroModeracionSalida],
    dependencies=[Depends(admin_o_contenido)],
)
async def cola_moderacion(
    pendientes: bool = True, repo: Repositorio = Depends(repositorio)
) -> list:
    return await repo.cola_moderacion(pendientes)


@router.post(
    "/moderacion/{registro_id}/revisado",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(admin_o_contenido)],
)
async def marcar_revisado(registro_id: uuid.UUID, repo: Repositorio = Depends(repositorio)):
    if not await repo.marcar_revisado(registro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "registro_inexistente")
