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
    # false = la cuenta queda confirmada al crearla y se puede entrar sin el correo de
    # verificación (p. ej. un piloto sin SMTP). El consentimiento sigue siendo obligatorio.
    verificar_correo: bool = True
    # Dominios que pueden crear cuenta, separados por coma. Vacío = cualquiera (por defecto:
    # limitarlo a Gmail y Hotmail es una decisión pendiente; se enciende con gmail.com,hotmail.com).
    dominios_correo: str = ""
    # Cómo abre la app el enlace de confirmación (esquema propio + paquete para Chrome)
    app_esquema: str = "storydraw"
    app_paquete_android: str = "com.storydraw.storydraw"
    version_consentimiento: str = "2026-10"
    admin_emails: str = ""
    contenido_emails: str = ""

    # Modo invitado: SOLO PRUEBAS LOCALES. Deja generar cuentos sin cuenta ni
    # consentimiento; el cuento no se guarda en el servidor (la app lo guarda en el
    # dispositivo). Apagado por defecto y prohibido con ENTORNO=produccion.
    permitir_invitados: bool = False
    invitado_minutos: int = Field(120, ge=5, le=24 * 60)
    # Lo no recogido por la app se descarta pasado este tiempo
    invitado_retencion_minutos: int = Field(30, ge=1, le=24 * 60)

    # Un adaptador por capacidad: cambiar de proveedor es cambiar esta variable
    # (ninguno = el proveedor no tiene esa capacidad y el paso se degrada)
    proveedor_vision: Literal["openai", "cloudflare", "ollama", "falso"] = "openai"
    proveedor_texto: Literal["openai", "cloudflare", "ollama", "falso"] = "openai"
    # ollama y cloudflare en moderación usan un LLM genérico: SOLO DESARROLLO
    proveedor_moderacion: Literal["openai", "llamaguard", "cloudflare", "ollama", "falso"] = (
        "openai"
    )
    proveedor_imagen: Literal["openai", "cloudflare", "ninguno", "falso"] = "openai"
    # cloudflare-aura = Deepgram Aura-2 (voz «javier», elegida por Josue el 2026-11-09);
    # cloudflare-melotts (o cloudflare, el nombre de antes) = MeloTTS; ninguno = sin audio
    proveedor_voz: Literal[
        "cloudflare-aura", "cloudflare-melotts", "cloudflare", "ninguno", "falso"
    ] = "ninguno"
    # ninguno = no se manda ningún correo (exige VERIFICAR_CORREO=false)
    proveedor_correo: Literal["smtp", "ninguno", "falso"] = "smtp"
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

    # Cloudflare Workers AI: modelos verificados en developers.cloudflare.com/workers-ai/models
    cloudflare_account_id: str = ""
    cloudflare_api_token: SecretStr | None = None
    cloudflare_modelo_vision: str = "@cf/google/gemma-4-26b-a4b-it"
    cloudflare_modelo_texto: str = "@cf/google/gemma-4-26b-a4b-it"
    cloudflare_modelo_moderacion: str = "@cf/google/gemma-4-26b-a4b-it"
    # Clasificador para PROVEEDOR_MODERACION=llamaguard (va junto a la revisión infantil)
    cloudflare_modelo_guardia: str = "@cf/meta/llama-guard-3-8b"
    cloudflare_modelo_imagen: str = "@cf/black-forest-labs/flux-1-schnell"
    cloudflare_pasos_imagen: int = Field(4, ge=1, le=8)
    # Envía chat_template_kwargs.enable_thinking=false (Gemma 4, Qwen 3). Ponlo en false
    # si el modelo de texto elegido no acepta ese campo.
    cloudflare_desactivar_razonamiento: bool = True
    # Tope por llamada (respuesta completa, cuerpo incluido). Lo normal es 2-18 s; si se
    # agota, el orquestador reintenta una sola vez y luego falla limpio (o se degrada).
    cloudflare_timeout_s: float = Field(45.0, gt=0)
    # Tarifa de neuronas y tarifas publicadas de cada modelo (cambian si cambias de modelo)
    cloudflare_usd_por_mil_neuronas: float = 0.011
    cloudflare_neuronas_texto_entrada_mtok: float = 9091.0
    cloudflare_neuronas_texto_salida_mtok: float = 27273.0
    cloudflare_neuronas_vision_entrada_mtok: float = 9091.0
    cloudflare_neuronas_vision_salida_mtok: float = 27273.0
    cloudflare_neuronas_imagen_tesela: float = 4.80
    cloudflare_neuronas_imagen_paso: float = 9.60
    # Voz. Vacío = el modelo del proveedor elegido: @cf/deepgram/aura-2-es (cloudflare-aura)
    # o @cf/myshell-ai/melotts (cloudflare-melotts).
    cloudflare_modelo_voz: str = ""
    # Hablante de Aura-2 (javier, alvaro, nestor, sirio, aquila...): javier = masculina cálida
    cloudflare_voz: str = "javier"
    # Aura-2 cobra por carácter: US$0,03 por 1.000 = 2.727 neuronas (a 0,011 USD las 1.000)
    cloudflare_neuronas_voz_mil_caracteres: float = 2727.27
    # MeloTTS: idioma y 18,63 neuronas por minuto de audio (tarifa publicada)
    cloudflare_idioma_voz: str = "es"
    cloudflare_neuronas_voz_minuto: float = 18.63

    # Ollama (prueba local, gratis, por CPU): texto, visión y moderación de desarrollo.
    # gemma3:4b ve imágenes, así que un solo modelo cubre las tres capacidades.
    ollama_url: str = "http://localhost:11434"
    ollama_modelo_texto: str = "gemma3:4b"
    ollama_modelo_vision: str = "gemma3:4b"
    ollama_modelo_moderacion: str = "gemma3:4b"
    ollama_timeout_s: float = 900.0

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
    # path = el bucket va en la ruta (MinIO y el gateway S3 de Hugging Face lo exigen)
    s3_estilo_direccion: Literal["path", "virtual", "auto"] = "path"
    # when_supported = lo que hace boto3 por defecto (CRC32 en cada petición). El gateway de
    # Hugging Face no entiende esas sumas: allí va when_required (solo si la operación las pide).
    s3_checksum: Literal["when_supported", "when_required"] = "when_supported"

    # Composición
    recorte: Literal["rembg", "umbral"] = "rembg"
    # Contraste mínimo dibujo/fondo (mediana de ΔE00): por debajo, el dibujo se confunde con
    # el fondo y la composición corrige la luz del fondo. 30 sale de lo medido el 2026-11-09.
    contraste_minimo_fondo: float = Field(30.0, ge=0, le=100)
    # true = antes de corregir, pide otro fondo (una vez por página). Apagado: en lo medido
    # el 2026-11-09 el segundo fondo casi nunca alcanzaba el mínimo (1 de 8) y sumaba ~5 s
    # y 57,6 neuronas por página; la corrección de luz sí llega siempre.
    regenerar_fondo_sin_contraste: bool = False

    # Orquestador
    reintentos_por_paso: int = Field(2, ge=0, le=5)
    espera_reintento_s: float = Field(0.5, ge=0)
    max_regeneraciones: int = Field(2, ge=0, le=5)
    timeout_proveedor_s: float = 60.0
    # Tope del cuento entero, para que nunca quede colgado. Vacío = automático: 180 s, o
    # sin tope si algún paso usa Ollama (por CPU tarda minutos).
    tiempo_maximo_cuento_s: float | None = Field(None, gt=0)
    max_dibujo_bytes: int = 5_000_000

    # Límite de tasa (por IP y por cuenta)
    limite_auth: str = "10/minute"
    limite_identificar: str = "10/minute"
    limite_cuentos_ip: str = "5/minute"
    limite_cuentos_cuenta: str = "30/day"
    limite_invitado_ip: str = "3/minute;20/day"

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
                    ("PROVEEDOR_MODERACION", self.proveedor_moderacion),
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
            if self.permitir_invitados:
                raise ValueError(
                    "PERMITIR_INVITADOS es solo para pruebas locales: "
                    "en producción no se permiten cuentos sin cuenta ni consentimiento"
                )
            if self.proveedor_moderacion in ("ollama", "cloudflare"):
                raise ValueError(
                    "La moderación con LLM genérico es solo para desarrollo: "
                    "en producción usa PROVEEDOR_MODERACION=openai o llamaguard"
                )
        proveedores = (
            self.proveedor_vision,
            self.proveedor_texto,
            self.proveedor_moderacion,
            self.proveedor_imagen,
            self.proveedor_voz,
        )
        if "openai" in proveedores and not self.openai_api_key:
            raise ValueError("Falta OPENAI_API_KEY (o usa PROVEEDOR_*=falso en desarrollo)")
        usa_cloudflare = any(p.startswith("cloudflare") for p in proveedores)
        if (usa_cloudflare or self.proveedor_moderacion == "llamaguard") and not (
            self.cloudflare_account_id and self.cloudflare_api_token
        ):
            raise ValueError("Faltan CLOUDFLARE_ACCOUNT_ID y CLOUDFLARE_API_TOKEN")
        if self.proveedor_correo == "ninguno" and self.verificar_correo:
            raise ValueError(
                "Con PROVEEDOR_CORREO=ninguno nadie podría confirmar su cuenta: "
                "pon VERIFICAR_CORREO=false o configura SMTP"
            )
        if self.proveedor_correo == "smtp" and not (self.smtp_host and self.smtp_remitente):
            raise ValueError("Faltan SMTP_HOST y SMTP_REMITENTE")
        if self.almacen == "s3" and not (self.s3_access_key and self.s3_secret_key):
            raise ValueError("Faltan S3_ACCESS_KEY y S3_SECRET_KEY")
        return self

    @staticmethod
    def _lista(valor: str) -> list[str]:
        return [x.strip().lower() for x in valor.split(",") if x.strip()]

    @property
    def lista_dominios_correo(self) -> list[str]:
        return [d.lstrip("@") for d in self._lista(self.dominios_correo)]

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
