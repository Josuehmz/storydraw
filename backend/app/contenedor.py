"""Ensamblado: elige un adaptador por capacidad según la configuración.

Es el único sitio que conoce las clases concretas. Para añadir un proveedor se escribe
su adaptador y se agrega una rama aquí; el pipeline no se toca.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.dominio.composicion import Compositor, RecortadorRembg, RecortadorUmbral
from app.dominio.costos import Tarifario
from app.dominio.moderacion import Moderacion
from app.dominio.orquestador import Orquestador
from app.dominio.puertos import IAlmacen, ICorreo, IImagen, IModerador, ITexto, IVision, IVoz
from app.infra.adaptadores.almacen import AlmacenMemoria, AlmacenS3
from app.infra.adaptadores.correo_smtp import CorreoSMTP
from app.infra.adaptadores.falsos import (
    CorreoFalso,
    ImagenFalsa,
    ImagenNoDisponible,
    TextoFalso,
    VisionFalsa,
    VozFalsa,
    VozNoDisponible,
)
from app.infra.adaptadores.moderacion_llm import ModeracionLLMSoloDesarrollo
from app.infra.adaptadores.proveedor_cloudflare import (
    ClienteCloudflare,
    ImagenCloudflare,
    TextoCloudflare,
    VisionCloudflare,
    VozCloudflare,
)
from app.infra.adaptadores.proveedor_ollama import ClienteOllama, TextoOllama, VisionOllama
from app.infra.adaptadores.proveedor_openai import ImagenOpenAI, TextoOpenAI, VisionOpenAI
from app.infra.bd import crear_fabrica, crear_motor
from app.infra.seguridad import Hasher, Tokens


@dataclass
class Contenedor:
    settings: Settings
    motor: AsyncEngine
    fabrica: async_sessionmaker[AsyncSession]
    vision: IVision
    texto: ITexto
    moderador: IModerador
    imagen: IImagen
    voz: IVoz
    correo: ICorreo
    almacen: IAlmacen
    orquestador: Orquestador
    hasher: Hasher
    tokens: Tokens
    http: httpx.AsyncClient

    async def cerrar(self) -> None:
        await self.http.aclose()
        await self.motor.dispose()


def _secreto(valor) -> str:
    return valor.get_secret_value() if valor is not None else ""


def construir(settings: Settings) -> Contenedor:
    http = httpx.AsyncClient(timeout=settings.timeout_proveedor_s)
    openai_cliente: AsyncOpenAI | None = None
    if settings.openai_api_key:
        openai_cliente = AsyncOpenAI(
            api_key=_secreto(settings.openai_api_key),
            timeout=settings.timeout_proveedor_s,
            max_retries=0,  # los reintentos los hace el orquestador, paso por paso
        )
    esfuerzo = settings.openai_esfuerzo_razonamiento

    cloudflare = ClienteCloudflare(
        http,
        settings.cloudflare_account_id,
        _secreto(settings.cloudflare_api_token),
        settings.cloudflare_timeout_s,
        settings.cloudflare_usd_por_mil_neuronas,
        (
            settings.cloudflare_neuronas_texto_entrada_mtok,
            settings.cloudflare_neuronas_texto_salida_mtok,
        ),
        settings.cloudflare_desactivar_razonamiento,
    )
    ollama = ClienteOllama(http, settings.ollama_url, settings.ollama_timeout_s)

    vision: IVision
    match settings.proveedor_vision:
        case "openai":
            vision = VisionOpenAI(openai_cliente, settings.openai_modelo_vision, esfuerzo)
        case "cloudflare":
            vision = VisionCloudflare(
                cloudflare,
                settings.cloudflare_modelo_vision,
                (
                    settings.cloudflare_neuronas_vision_entrada_mtok,
                    settings.cloudflare_neuronas_vision_salida_mtok,
                ),
            )
        case "ollama":
            vision = VisionOllama(ollama, settings.ollama_modelo_vision)
        case _:
            vision = VisionFalsa()

    texto: ITexto
    match settings.proveedor_texto:
        case "openai":
            texto = TextoOpenAI(
                openai_cliente,
                settings.openai_modelo_texto,
                settings.openai_modelo_moderacion,
                esfuerzo,
            )
        case "cloudflare":
            texto = TextoCloudflare(cloudflare, settings.cloudflare_modelo_texto)
        case "ollama":
            texto = TextoOllama(ollama, settings.ollama_modelo_texto)
        case _:
            texto = TextoFalso()

    moderador: IModerador
    match settings.proveedor_moderacion:
        case "openai":
            moderador = (
                texto
                if isinstance(texto, TextoOpenAI)
                else TextoOpenAI(
                    openai_cliente,
                    settings.openai_modelo_texto,
                    settings.openai_modelo_moderacion,
                )
            )
        case "cloudflare":
            moderador = ModeracionLLMSoloDesarrollo(
                cloudflare, settings.cloudflare_modelo_moderacion
            )
        case "ollama":
            moderador = ModeracionLLMSoloDesarrollo(ollama, settings.ollama_modelo_moderacion)
        case _:
            # El falso de texto también modera: si ambos son falsos, es la misma instancia.
            moderador = texto if isinstance(texto, TextoFalso) else TextoFalso()

    imagen: IImagen
    match settings.proveedor_imagen:
        case "openai":
            imagen = ImagenOpenAI(
                openai_cliente,
                settings.openai_modelo_imagen,
                settings.openai_calidad_imagen,
                settings.openai_tamano_imagen,
            )
        case "cloudflare":
            imagen = ImagenCloudflare(
                cloudflare,
                settings.cloudflare_modelo_imagen,
                settings.cloudflare_pasos_imagen,
                settings.cloudflare_neuronas_imagen_tesela,
                settings.cloudflare_neuronas_imagen_paso,
            )
        case "ninguno":
            imagen = ImagenNoDisponible()
        case _:
            imagen = ImagenFalsa()

    voz: IVoz
    match settings.proveedor_voz:
        case "cloudflare":
            voz = VozCloudflare(
                cloudflare,
                settings.cloudflare_modelo_voz,
                settings.cloudflare_idioma_voz,
                settings.cloudflare_neuronas_voz_minuto,
            )
        case "falso":
            voz = VozFalsa()
        case _:
            voz = VozNoDisponible()

    correo: ICorreo = (
        CorreoSMTP(
            settings.smtp_host,
            settings.smtp_puerto,
            settings.smtp_usuario,
            _secreto(settings.smtp_contrasena),
            settings.smtp_remitente,
            settings.smtp_seguridad,
        )
        if settings.proveedor_correo == "smtp"
        else CorreoFalso()
    )
    almacen: IAlmacen = (
        AlmacenS3(
            settings.s3_bucket,
            _secreto(settings.s3_access_key),
            _secreto(settings.s3_secret_key),
            settings.s3_region,
            settings.s3_endpoint_url,
            settings.s3_cifrado_sse,
        )
        if settings.almacen == "s3"
        else AlmacenMemoria()
    )
    recortador = RecortadorRembg() if settings.recorte == "rembg" else RecortadorUmbral()
    tarifario = Tarifario(
        texto_entrada_mtok=settings.precio_texto_entrada_mtok,
        texto_salida_mtok=settings.precio_texto_salida_mtok,
        vision_entrada_mtok=settings.precio_vision_entrada_mtok,
        vision_salida_mtok=settings.precio_vision_salida_mtok,
        imagen=settings.precio_imagen,
        voz_mil_caracteres=settings.precio_voz_mil_caracteres,
    )
    orquestador = Orquestador(
        vision=vision,
        texto=texto,
        imagen=imagen,
        voz=voz,
        moderacion=Moderacion(moderador),
        compositor=Compositor(recortador),
        almacen=almacen,
        tarifario=tarifario,
        reintentos=settings.reintentos_por_paso,
        espera_base_s=settings.espera_reintento_s,
        max_regeneraciones=settings.max_regeneraciones,
        timeout_s=settings.timeout_proveedor_s,
    )
    motor = crear_motor(settings.database_url)
    return Contenedor(
        settings=settings,
        motor=motor,
        fabrica=crear_fabrica(motor),
        vision=vision,
        texto=texto,
        moderador=moderador,
        imagen=imagen,
        voz=voz,
        correo=correo,
        almacen=almacen,
        orquestador=orquestador,
        hasher=Hasher(),
        tokens=Tokens(
            settings.jwt_secreto.get_secret_value(),
            settings.jwt_minutos,
            settings.verificacion_horas,
        ),
        http=http,
    )
