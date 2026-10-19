"""Casos de uso que combinan el orquestador, el repositorio y el almacén."""

from __future__ import annotations

import logging
import uuid

from app.api.esquemas import CuentoResumen, CuentoSalida, PaginaSalida
from app.contenedor import Contenedor
from app.dominio.orquestador import AVISO_SIN_NARRACION, MetricaPaso, ResultadoCuento, clave_audio
from app.infra.orm import Cuento
from app.infra.repositorio import Repositorio

log = logging.getLogger(__name__)


def url_imagen(cuento_id: uuid.UUID, numero: int) -> str:
    return f"/v1/cuentos/{cuento_id}/paginas/{numero}/imagen"


def url_audio(cuento_id: uuid.UUID, numero: int) -> str:
    return f"/v1/cuentos/{cuento_id}/paginas/{numero}/audio"


def a_salida(cuento: Cuento) -> CuentoSalida:
    # Mientras no está listo (moderación incluida), no se expone ninguna página.
    paginas = []
    if cuento.estado == "listo":
        paginas = [
            PaginaSalida(
                numero=p.numero,
                texto=p.texto,
                imagen_url=url_imagen(cuento.id, p.numero),
                audio_url=url_audio(cuento.id, p.numero) if p.audio_clave else None,
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
    c: Contenedor, cuento_id: uuid.UUID, dibujo_png: bytes, personaje: str | None, edad: int
) -> None:
    """Tarea en segundo plano. El dibujo solo vive en esta llamada, en memoria."""
    try:
        resultado = await c.orquestador.crear_cuento(str(cuento_id), dibujo_png, personaje, edad)
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


async def reintentar_narracion(c: Contenedor, repo: Repositorio, cuento: Cuento) -> Cuento:
    """Reintenta solo el paso de voz de las páginas que quedaron sin audio."""
    pendientes = [p for p in cuento.paginas if not p.audio_clave]
    if not pendientes:
        return cuento
    metrica = MetricaPaso("narrar_reintento", c.voz.proveedor)
    audios = await c.orquestador.narrar([p.texto for p in pendientes], metrica)
    for pagina, audio in zip(pendientes, audios, strict=True):
        if audio is not None:
            clave = clave_audio(str(cuento.id), pagina.numero)
            await c.almacen.guardar(clave, audio, "audio/mpeg")
            pagina.audio_clave = clave
    if all(p.audio_clave for p in cuento.paginas):
        cuento.avisos = [a for a in (cuento.avisos or []) if a != AVISO_SIN_NARRACION]
    cuento.pasos = [*list(cuento.pasos or []), metrica.como_dict()]
    cuento.costo_usd = round((cuento.costo_usd or 0) + metrica.costo_usd, 6)
    await repo.s.commit()
    return cuento


async def borrar_cuentos(c: Contenedor, ids: list[uuid.UUID]) -> None:
    for cuento_id in ids:
        await c.almacen.borrar_prefijo(f"cuentos/{cuento_id}/")
