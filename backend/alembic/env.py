"""Entorno de Alembic (async). La URL sale de DATABASE_URL, nunca de alembic.ini."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.config import ConfigBD
from app.infra.bd import crear_motor
from app.infra.orm import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configurar_logs", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("database_url") or ConfigBD().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _ejecutar(conexion: Connection) -> None:
    context.configure(
        connection=conexion,
        target_metadata=target_metadata,
        render_as_batch=conexion.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def _online() -> None:
    motor = crear_motor(_url())
    async with motor.connect() as conexion:
        await conexion.run_sync(_ejecutar)
    await motor.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_online())
