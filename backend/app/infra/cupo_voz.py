"""Tope diario de cuentos con voz, contado en la base de datos por día UTC.

La voz Aura-2 cuesta unas 2.150 neuronas por cuento y el plan gratuito de Cloudflare da 10.000
al día (compartidas con producción), así que la voz se enciende limitada: «Se enciende limitada,
se permanece en plan gratuito» (Josue, 2026-11-09). El día es UTC porque Cloudflare documenta
que su cupo se repone a las 00:00 UTC (19:00 en Colombia). En la práctica puede tardar más (el
2026-11-10 seguía agotado pasadas las 00:25 UTC); para eso está la reserva ante el 429 del
orquestador, que corta la voz sin romper el cuento.

La reserva es una sola sentencia atómica (`INSERT ... ON CONFLICT DO UPDATE ... WHERE usados <
tope RETURNING`): dos cuentos a la vez no pueden pasarse del tope, ni en PostgreSQL (bloquea la
fila) ni en SQLite (serializa las escrituras).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as insert_pg
from sqlalchemy.dialects.sqlite import insert as insert_sqlite
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dominio.orquestador import hoy_utc
from app.dominio.puertos import ICupoVoz
from app.infra.orm import CupoVoz

log = logging.getLogger(__name__)

SIN_TOPE = -1


def consulta_reserva(dialecto: str, dia: date, tope: int):
    """`INSERT ... ON CONFLICT (dia) DO UPDATE SET usados = usados + 1 WHERE usados < tope
    RETURNING usados`: devuelve la cuenta nueva o nada si ya se llegó al tope."""
    insertar = insert_pg if dialecto == "postgresql" else insert_sqlite
    return (
        insertar(CupoVoz)
        .values(dia=dia, usados=1)
        .on_conflict_do_update(
            index_elements=[CupoVoz.dia],
            set_={"usados": CupoVoz.usados + 1},
            where=CupoVoz.usados < tope,
        )
        .returning(CupoVoz.usados)
    )


class CupoVozBD(ICupoVoz):
    """`tope` cuentos con voz por día UTC. 0 = ninguno; -1 (`SIN_TOPE`) = sin límite."""

    def __init__(
        self,
        fabrica: async_sessionmaker[AsyncSession],
        tope: int,
        reloj: Callable[[], date] = hoy_utc,
    ):
        self._fabrica = fabrica
        self.tope = tope
        self._reloj = reloj

    async def reservar(self) -> bool:
        if self.tope == SIN_TOPE:
            return True
        if self.tope <= 0:
            return False
        dia = self._reloj()
        async with self._fabrica() as s:
            consulta = consulta_reserva(s.bind.dialect.name, dia, self.tope)
            usados = (await s.execute(consulta)).scalar_one_or_none()
            await s.commit()
        if usados is None:
            log.info("cupo_voz dia=%s agotado tope=%d", dia, self.tope)
            return False
        log.info("cupo_voz dia=%s usados=%d tope=%d", dia, usados, self.tope)
        return True

    async def liberar(self) -> None:
        if self.tope <= 0:
            return
        async with self._fabrica() as s:
            await s.execute(
                update(CupoVoz)
                .where(CupoVoz.dia == self._reloj(), CupoVoz.usados > 0)
                .values(usados=CupoVoz.usados - 1)
            )
            await s.commit()

    async def usados_hoy(self) -> int:
        async with self._fabrica() as s:
            fila = await s.get(CupoVoz, self._reloj())
            return fila.usados if fila else 0
