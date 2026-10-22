"""Configuración única del backend.

Todo valor externo (claves, URLs, modelos, precios, límites) entra por aquí y por ningún
otro sitio. Si falta algo obligatorio, el servicio falla al arrancar con un mensaje claro,
antes de gastar en ningún proveedor.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_RAIZ_BACKEND = Path(__file__).resolve().parent.parent
_ARCHIVOS_ENV = (_RAIZ_BACKEND.parent / ".env", _RAIZ_BACKEND / ".env")

URL_BD_POR_DEFECTO = "postgresql+asyncpg://storydraw:storydraw@localhost:5432/storydraw"


class ConfigBD(BaseSettings):
    """Lo mínimo que necesita Alembic: solo la URL de la base de datos."""

    model_config = SettingsConfigDict(
        env_file=_ARCHIVOS_ENV, env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    database_url: str = URL_BD_POR_DEFECTO


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ARCHIVOS_ENV, env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    entorno: Literal["desarrollo", "pruebas", "produccion"] = "desarrollo"
    database_url: str = URL_BD_POR_DEFECTO
    url_publica: str = "http://localhost:8000"
    cors_origenes: str = ""

    # Cuentas
    jwt_secreto: SecretStr = Field(..., min_length=32)
    jwt_minutos: int = 60 * 24
    verificacion_horas: int = 48
    version_consentimiento: str = "2026-10"
    admin_emails: str = ""
    contenido_emails: str = ""

    # Un adaptador por capacidad: cambiar de proveedor es cambiar esta variable
    proveedor_vision: Literal["openai", "falso"] = "openai"
    proveedor_texto: Literal["openai", "falso"] = "openai"
    proveedor_imagen: Literal["openai", "falso"] = "openai"
    proveedor_voz: Literal["elevenlabs", "falso"] = "elevenlabs"
    proveedor_correo: Literal["smtp", "falso"] = "smtp"
    almacen: Literal["s3", "memoria"] = "s3"

    # OpenAI: visión, cuento, moderación e imagen con una sola clave
    openai_api_key: SecretStr | None = None
    openai_modelo_vision: str = "gpt-5.6-luna"
    openai_modelo_texto: str = "gpt-5.6-luna"
    openai_modelo_moderacion: str = "omni-moderation-latest"
    openai_modelo_imagen: str = "gpt-image-1-mini"
    openai_calidad_imagen: str = "low"
    openai_tamano_imagen: str = "1024x1024"
    openai_esfuerzo_razonamiento: str = "low"

    # ElevenLabs: narración
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voz_id: str = ""
    elevenlabs_modelo: str = "eleven_flash_v2_5"

    # Correo transaccional
    smtp_host: str = ""
    smtp_puerto: int = 587
    smtp_usuario: str = ""
    smtp_contrasena: SecretStr | None = None
    smtp_remitente: str = ""
    smtp_seguridad: Literal["starttls", "ssl", "ninguna"] = "starttls"

    # Almacenamiento S3 compatible
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "storydraw"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_cifrado_sse: bool = True

    # Composición
    recorte: Literal["rembg", "umbral"] = "rembg"

    # Orquestador
    reintentos_por_paso: int = Field(2, ge=0, le=5)
    espera_reintento_s: float = Field(0.5, ge=0)
    max_regeneraciones: int = Field(2, ge=0, le=5)
    timeout_proveedor_s: float = 60.0
    max_dibujo_bytes: int = 5_000_000

    # Límite de tasa (por IP y por cuenta)
    limite_auth: str = "10/minute"
    limite_identificar: str = "10/minute"
    limite_cuentos_ip: str = "5/minute"
    limite_cuentos_cuenta: str = "30/day"

    # Tarifas en USD (para el costo por cuento del panel de operación)
    precio_texto_entrada_mtok: float = 0.20
    precio_texto_salida_mtok: float = 1.20
    precio_vision_entrada_mtok: float = 0.20
    precio_vision_salida_mtok: float = 1.20
    precio_imagen: float = 0.005
    precio_voz_mil_caracteres: float = 0.05

    @model_validator(mode="after")
    def _validar(self) -> Settings:
        if self.entorno == "produccion":
            falsos = [
                nombre
                for nombre, valor in (
                    ("PROVEEDOR_VISION", self.proveedor_vision),
                    ("PROVEEDOR_TEXTO", self.proveedor_texto),
                    ("PROVEEDOR_IMAGEN", self.proveedor_imagen),
                    ("PROVEEDOR_VOZ", self.proveedor_voz),
                    ("PROVEEDOR_CORREO", self.proveedor_correo),
                )
                if valor == "falso"
            ]
            if falsos:
                raise ValueError(f"En producción no se permiten adaptadores falsos: {falsos}")
            if self.almacen == "memoria":
                raise ValueError("En producción ALMACEN debe ser s3")
        usa_openai = "openai" in (
            self.proveedor_vision,
            self.proveedor_texto,
            self.proveedor_imagen,
        )
        if usa_openai and not self.openai_api_key:
            raise ValueError("Falta OPENAI_API_KEY (o usa PROVEEDOR_*=falso en desarrollo)")
        if self.proveedor_voz == "elevenlabs" and not (
            self.elevenlabs_api_key and self.elevenlabs_voz_id
        ):
            raise ValueError("Faltan ELEVENLABS_API_KEY y ELEVENLABS_VOZ_ID")
        if self.proveedor_correo == "smtp" and not (self.smtp_host and self.smtp_remitente):
            raise ValueError("Faltan SMTP_HOST y SMTP_REMITENTE")
        if self.almacen == "s3" and not (self.s3_access_key and self.s3_secret_key):
            raise ValueError("Faltan S3_ACCESS_KEY y S3_SECRET_KEY")
        return self

    @staticmethod
    def _lista(valor: str) -> list[str]:
        return [x.strip().lower() for x in valor.split(",") if x.strip()]

    @property
    def lista_admin(self) -> list[str]:
        return self._lista(self.admin_emails)

    @property
    def lista_contenido(self) -> list[str]:
        return self._lista(self.contenido_emails)

    @property
    def lista_cors(self) -> list[str]:
        return [x.strip() for x in self.cors_origenes.split(",") if x.strip()]


@lru_cache
def obtener_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
