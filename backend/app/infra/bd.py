"""Motor y sesiones de SQLAlchemy 2 (async)."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def _activar_fk(conexion, _registro) -> None:
    # SQLite no aplica las claves foráneas (ni el borrado en cascada) si no se pide.
    cursor = conexion.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def crear_motor(url: str) -> AsyncEngine:
    if not url.startswith("sqlite"):
        return create_async_engine(url, pool_pre_ping=True)
    # SQLite (pruebas y desarrollo): sin pool, para no compartir conexiones entre bucles.
    motor = create_async_engine(url, poolclass=NullPool)
    event.listen(motor.sync_engine, "connect", _activar_fk)
    return motor


def crear_fabrica(motor: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(motor, expire_on_commit=False)
