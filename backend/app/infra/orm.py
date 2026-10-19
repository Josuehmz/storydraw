"""Esquema `storydraw`: perfiles, consentimientos, cuentos y registro de moderación.

El dibujo del niño no tiene tabla: nunca se persiste. Lo que queda es el cuento.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def ahora() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tutor(Base):
    """El responsable del menor: la cuenta que inicia sesión."""

    __tablename__ = "tutores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hash_contrasena: Mapped[str] = mapped_column(String(255))
    verificado: Mapped[bool] = mapped_column(Boolean, default=False)
    rol: Mapped[str] = mapped_column(String(20), default="tutor")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    consentimientos: Mapped[list[Consentimiento]] = relationship(
        back_populates="tutor", cascade="all, delete-orphan", passive_deletes=True
    )
    perfiles: Mapped[list[Perfil]] = relationship(
        back_populates="tutor", cascade="all, delete-orphan", passive_deletes=True
    )


class Consentimiento(Base):
    __tablename__ = "consentimientos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tutores.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(20))
    aceptado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    tutor: Mapped[Tutor] = relationship(back_populates="consentimientos")


class Perfil(Base):
    """Un niño. Solo apodo y edad: minimización de datos."""

    __tablename__ = "perfiles"
    __table_args__ = (CheckConstraint("edad BETWEEN 6 AND 12", name="ck_perfiles_edad"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tutores.id", ondelete="CASCADE"), index=True
    )
    apodo: Mapped[str] = mapped_column(String(40))
    edad: Mapped[int] = mapped_column(SmallInteger)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    tutor: Mapped[Tutor] = relationship(back_populates="perfiles")


class Cuento(Base):
    __tablename__ = "cuentos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    perfil_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfiles.id", ondelete="CASCADE"), index=True
    )
    tutor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tutores.id", ondelete="CASCADE"), index=True
    )
    estado: Mapped[str] = mapped_column(String(20), default="en_proceso", index=True)
    titulo: Mapped[str | None] = mapped_column(String(200))
    personaje: Mapped[str | None] = mapped_column(String(120))
    avisos: Mapped[list] = mapped_column(JSON, default=list)
    pasos: Mapped[list] = mapped_column(JSON, default=list)
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    costo_usd: Mapped[float | None] = mapped_column(Float)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    paginas: Mapped[list[Pagina]] = relationship(
        back_populates="cuento",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Pagina.numero",
        lazy="selectin",
    )


class Pagina(Base):
    __tablename__ = "paginas"
    __table_args__ = (UniqueConstraint("cuento_id", "numero", name="uq_pagina_numero"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cuento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cuentos.id", ondelete="CASCADE"), index=True
    )
    numero: Mapped[int] = mapped_column(SmallInteger)
    texto: Mapped[str] = mapped_column(Text)
    imagen_clave: Mapped[str] = mapped_column(String(255))
    audio_clave: Mapped[str | None] = mapped_column(String(255))

    cuento: Mapped[Cuento] = relationship(back_populates="paginas")


class RegistroModeracion(Base):
    """Lo rechazado, para la cola de revisión del equipo de contenido."""

    __tablename__ = "registros_moderacion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cuento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cuentos.id", ondelete="SET NULL"), index=True
    )
    origen: Mapped[str] = mapped_column(String(20))
    texto: Mapped[str | None] = mapped_column(Text)
    categorias: Mapped[list] = mapped_column(JSON, default=list)
    revisado: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
