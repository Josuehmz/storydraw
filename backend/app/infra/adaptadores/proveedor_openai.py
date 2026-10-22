"""Adaptadores de OpenAI: IVision, ITexto (cuento y moderación) e IImagen.

Una sola clave (`OPENAI_API_KEY`) y un modelo por variable de entorno para cada capacidad.
"""

from __future__ import annotations

import base64
import json

from openai import AsyncOpenAI

from app.dominio.puertos import (
    CuentoTexto,
    Hipotesis,
    IImagen,
    IModerador,
    ITexto,
    IVision,
    PaginaTexto,
    ResultadoImagen,
    ResultadoVision,
    SolicitudCuento,
    Uso,
    VeredictoModeracion,
)
from app.infra.adaptadores.comun import ESQUEMA_CUENTO as _ESQUEMA_CUENTO
from app.infra.adaptadores.comun import ESQUEMA_VISION as _ESQUEMA_VISION
from app.infra.adaptadores.comun import PROMPT_VISION as _PROMPT_VISION
from app.infra.adaptadores.comun import atributos_desde, mensaje_solicitud


def _uso_chat(respuesta) -> Uso:
    uso = getattr(respuesta, "usage", None)
    if uso is None:
        return Uso()
    return Uso(tokens_entrada=uso.prompt_tokens or 0, tokens_salida=uso.completion_tokens or 0)


class _BaseOpenAI:
    proveedor = "openai"

    def __init__(self, cliente: AsyncOpenAI, modelo: str, esfuerzo: str = ""):
        self._cliente = cliente
        self._modelo = modelo
        self._extra = {"reasoning_effort": esfuerzo} if esfuerzo else {}


class VisionOpenAI(_BaseOpenAI, IVision):
    async def identificar(self, imagen_png: bytes) -> ResultadoVision:
        url = "data:image/png;base64," + base64.b64encode(imagen_png).decode()
        respuesta = await self._cliente.chat.completions.create(
            model=self._modelo,
            messages=[
                {"role": "system", "content": _PROMPT_VISION},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "¿Qué dibujó el niño?"},
                        {"type": "image_url", "image_url": {"url": url, "detail": "low"}},
                    ],
                },
            ],
            response_format={"type": "json_schema", "json_schema": _ESQUEMA_VISION},
            **self._extra,
        )
        datos = json.loads(respuesta.choices[0].message.content or "{}")
        hipotesis = [
            Hipotesis(str(h["etiqueta"]), float(h["confianza"])) for h in datos.get("hipotesis", [])
        ]
        return ResultadoVision(hipotesis, _uso_chat(respuesta), atributos_desde(datos))


class TextoOpenAI(_BaseOpenAI, ITexto, IModerador):
    def __init__(self, cliente: AsyncOpenAI, modelo: str, modelo_moderacion: str, esfuerzo=""):
        super().__init__(cliente, modelo, esfuerzo)
        self._modelo_moderacion = modelo_moderacion

    async def escribir_cuento(self, solicitud: SolicitudCuento) -> CuentoTexto:
        respuesta = await self._cliente.chat.completions.create(
            model=self._modelo,
            messages=[
                {
                    "role": "system",
                    "content": mensaje_solicitud(solicitud),
                },
                {"role": "user", "content": f"Protagonista: {solicitud.personaje}"},
            ],
            response_format={"type": "json_schema", "json_schema": _ESQUEMA_CUENTO},
            **self._extra,
        )
        datos = json.loads(respuesta.choices[0].message.content or "{}")
        paginas = [PaginaTexto(p["texto"], p["escena"]) for p in datos.get("paginas", [])]
        return CuentoTexto(datos.get("titulo", ""), paginas, _uso_chat(respuesta))

    async def moderar(self, texto: str) -> VeredictoModeracion:
        respuesta = await self._cliente.moderations.create(
            model=self._modelo_moderacion, input=texto
        )
        resultado = respuesta.results[0]
        categorias = [
            nombre for nombre, marcado in resultado.categories.model_dump().items() if marcado
        ]
        return VeredictoModeracion(not resultado.flagged, categorias, Uso())


class ImagenOpenAI(_BaseOpenAI, IImagen):
    def __init__(self, cliente: AsyncOpenAI, modelo: str, calidad: str, tamano: str):
        super().__init__(cliente, modelo)
        self._calidad = calidad
        self._tamano = tamano

    async def generar_fondo(self, descripcion: str) -> ResultadoImagen:
        prompt = (
            "Children's picture-book background illustration, soft colors, no characters, "
            f"no people, no animals, no text. Scene: {descripcion}"
        )
        respuesta = await self._cliente.images.generate(
            model=self._modelo,
            prompt=prompt,
            size=self._tamano,
            quality=self._calidad,
            n=1,
        )
        b64 = respuesta.data[0].b64_json if respuesta.data else None
        if not b64:
            raise RuntimeError("la API de imágenes no devolvió datos")
        return ResultadoImagen(base64.b64decode(b64), Uso(imagenes=1))
