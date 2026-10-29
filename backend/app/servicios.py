"""Casos de uso que combinan el orquestador, el repositorio y el almacén."""

from __future__ import annotations

import logging
import uuid

from app.api.esquemas import CuentoResumen, CuentoSalida, PaginaSalida
from app.contenedor import Contenedor
from app.dominio.orquestador import ResultadoCuento
from app.infra.orm import Cuento
from app.infra.repositorio import Repositorio

log = logging.getLogger(__name__)


def url_imagen(cuento_id: uuid.UUID, numero: int) -> str:
    return f"/v1/cuentos/{cuento_id}/paginas/{numero}/imagen"


def a_salida(cuento: Cuento) -> CuentoSalida:
    # Mientras no está listo (moderación incluida), no se expone ninguna página.
    paginas = []
    if cuento.estado == "listo":
        paginas = [
            PaginaSalida(
                numero=p.numero,
                texto=p.texto,
                imagen_url=url_imagen(cuento.id, p.numero),
            )
            for p in cuento.paginas
        ]
    return CuentoSalida(
        id=cuento.id,
        perfil_id=cuento.perfil_id,
        estado=cuento.estado,  # type: ignore[arg-type]
        titulo=cuento.titulo if cuento.estado == "listo" else None,
        personaje=cuento.personaje if cuento.estado == "listo" else None,
        avisos=list(cuento.avisos or []),
        paginas=paginas,
        creado_en=cuento.creado_en,
    )


def a_resumen(cuento: Cuento) -> CuentoResumen:
    return CuentoResumen(
        id=cuento.id,
        titulo=cuento.titulo,
        personaje=cuento.personaje,
        portada_url=url_imagen(cuento.id, 1) if cuento.paginas else None,
        creado_en=cuento.creado_en,
    )


async def procesar_cuento(
    c: Contenedor,
    cuento_id: uuid.UUID,
    dibujo_png: bytes,
    personaje: str | None,
    edad: int,
    nombre: str | None = None,
) -> None:
    """Tarea en segundo plano. El dibujo solo vive en esta llamada, en memoria."""
    try:
        resultado = await c.orquestador.crear_cuento(
            str(cuento_id), dibujo_png, personaje, edad, nombre
        )
    except Exception:
        log.exception("cuento=%s fallo inesperado del orquestador", cuento_id)
        resultado = ResultadoCuento(estado="fallido")
    finally:
        del dibujo_png
    if resultado.estado != "listo":
        await c.almacen.borrar_prefijo(f"cuentos/{cuento_id}/")
    async with c.fabrica() as s:
        await Repositorio(s).guardar_resultado(cuento_id, resultado)
    log.info(
        "cuento=%s estado=%s latencia_ms=%d costo_usd=%.5f avisos=%s",
        cuento_id,
        resultado.estado,
        resultado.latencia_ms,
        resultado.costo_usd,
        ",".join(resultado.avisos),
    )


async def borrar_cuentos(c: Contenedor, ids: list[uuid.UUID]) -> None:
    for cuento_id in ids:
        await c.almacen.borrar_prefijo(f"cuentos/{cuento_id}/")
