"""Contratos HTTP (Pydantic v2). Son el contrato estable con la app Flutter."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegistroEntrada(BaseModel):
    email: EmailStr
    contrasena: str = Field(min_length=10, max_length=128)
    acepta_consentimiento: bool = Field(
        description="El responsable acepta el tratamiento de datos del menor. Debe ser true."
    )

    @field_validator("acepta_consentimiento")
    @classmethod
    def _debe_aceptar(cls, valor: bool) -> bool:
        if valor is not True:
            raise ValueError("Se necesita el consentimiento del responsable")
        return valor


class RegistroSalida(BaseModel):
    id: uuid.UUID
    email: EmailStr
    verificado: bool
    version_consentimiento: str
    # False = la cuenta se creó pero el correo no salió: la app ofrece «Reenviar correo»
    correo_enviado: bool = True


class LoginEntrada(BaseModel):
    email: EmailStr
    contrasena: str = Field(max_length=128)


class TokenSalida(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - no es una contraseña
    expira_en: int
    rol: str


class PerfilEntrada(BaseModel):
    apodo: str = Field(min_length=1, max_length=40)
    edad: int = Field(ge=6, le=12)


class PerfilSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apodo: str
    edad: int
    creado_en: datetime


class HipotesisSalida(BaseModel):
    etiqueta: str
    confianza: float = Field(ge=0, le=1)


class IdentificacionSalida(BaseModel):
    disponible: bool
    hipotesis: list[HipotesisSalida]


class CuentoCreado(BaseModel):
    id: uuid.UUID
    estado: str


class PaginaSalida(BaseModel):
    numero: int
    texto: str
    imagen_url: str
    # None = esta página no tiene narración (voz apagada o falló); la app no muestra el botón
    audio_url: str | None = None


class CuentoSalida(BaseModel):
    id: uuid.UUID
    perfil_id: uuid.UUID
    estado: Literal["en_proceso", "listo", "rechazado", "fallido"]
    titulo: str | None
    personaje: str | None
    avisos: list[str]
    paginas: list[PaginaSalida]
    creado_en: datetime


class CuentoResumen(BaseModel):
    id: uuid.UUID
    titulo: str | None
    personaje: str | None
    portada_url: str | None
    creado_en: datetime


class PasoMetrica(BaseModel):
    paso: str
    proveedor: str
    estado: str
    intentos: int
    latencia_ms: int
    costo_usd: float


class CuentoMetrica(BaseModel):
    id: uuid.UUID
    estado: str
    latencia_ms: int | None
    costo_usd: float | None
    avisos: list[str]
    pasos: list[PasoMetrica]
    creado_en: datetime


class ResumenOperacion(BaseModel):
    cuentos: int
    por_estado: dict[str, int]
    latencia_media_ms: float | None
    latencia_p95_ms: float | None
    costo_medio_usd: float | None
    costo_total_usd: float
    degradaciones: dict[str, int]


class RegistroModeracionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cuento_id: uuid.UUID | None
    origen: str
    texto: str | None
    categorias: list[str]
    revisado: bool
    creado_en: datetime
