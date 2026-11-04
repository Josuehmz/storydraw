"""Motor y sesiones de SQLAlchemy 2 (async)."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import make_url
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


# Parámetros de libpq (los que trae la cadena de Neon) que asyncpg no entiende.
_SOLO_LIBPQ = ("channel_binding", "options", "target_session_attrs")


def normalizar_url_bd(url: str) -> str:
    """Acepta la cadena tal como la da el proveedor (Neon, Supabase...) y la deja para asyncpg.

    - `postgres://` o `postgresql://` → `postgresql+asyncpg://`.
    - `sslmode=require` → `ssl=require` (asyncpg no conoce `sslmode`).
    - Quita `channel_binding` y otros parámetros que solo entiende libpq.
    SQLite y las URLs que ya traen su driver quedan igual, salvo esos parámetros.
    """
    if url.startswith("sqlite"):
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    destino = make_url(url)
    if destino.drivername == "postgresql":
        destino = destino.set(drivername="postgresql+asyncpg")
    if not destino.drivername.endswith("+asyncpg"):
        return destino.render_as_string(hide_password=False)
    consulta = dict(destino.query)
    if "sslmode" in consulta:
        consulta.setdefault("ssl", consulta.pop("sslmode"))
    for clave in _SOLO_LIBPQ:
        consulta.pop(clave, None)
    return destino.set(query=consulta).render_as_string(hide_password=False)


def crear_motor(url: str) -> AsyncEngine:
    url = normalizar_url_bd(url)
    if not url.startswith("sqlite"):
        return create_async_engine(url, pool_pre_ping=True)
    # SQLite (pruebas y desarrollo): sin pool, para no compartir conexiones entre bucles.
    motor = create_async_engine(url, poolclass=NullPool)
    event.listen(motor.sync_engine, "connect", _activar_fk)
    return motor


def crear_fabrica(motor: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(motor, expire_on_commit=False)
