"""Moderación para producción sin OpenAI: Llama Guard 3 en Cloudflare Workers AI, más una
revisión de idoneidad infantil con LLM.

Llama Guard es un clasificador de seguridad (taxonomía S1–S14 de MLCommons), pero no piensa
en niños: en las pruebas reales dejó pasar violencia narrada y una escena sexual descrita sin
palabras explícitas. Por eso se combina con la revisión infantil del LLM (el mismo prompt de
`moderacion_llm`), y con la lista local de `Moderacion`, que ya corre antes. Las dos capas
tienen que aprobar.

Falla cerrada: si cualquiera de las dos no responde, tarda de más o devuelve algo ilegible,
se lanza una excepción y el orquestador trata el cuento como no aprobado. De Llama Guard solo
aprueba `"safe": true` (booleano) o la respuesta de texto exacta «safe».
"""

from __future__ import annotations

import asyncio

from app.dominio.puertos import IModerador, Uso, VeredictoModeracion
from app.infra.adaptadores.comun import ErrorProveedor
from app.infra.adaptadores.moderacion_llm import ModeracionLLMSoloDesarrollo
from app.infra.adaptadores.proveedor_cloudflare import ClienteCloudflare


def leer_veredicto_guardia(respuesta: object) -> tuple[bool, list[str]]:
    """Interpreta la salida de Llama Guard. Todo lo que no sea «seguro» claro, no aprueba."""
    if isinstance(respuesta, dict):
        seguro = respuesta.get("safe")
        if not isinstance(seguro, bool):
            raise ErrorProveedor("Llama Guard respondió sin el campo booleano «safe»")
        categorias = respuesta.get("categories") or []
        if not isinstance(categorias, list):
            categorias = [str(categorias)]
        return seguro, [str(c) for c in categorias]
    if isinstance(respuesta, str):
        lineas = [linea.strip() for linea in respuesta.strip().splitlines() if linea.strip()]
        if lineas and lineas[0].lower() == "safe":
            return True, []
        if lineas and lineas[0].lower() == "unsafe":
            return False, [c.strip() for linea in lineas[1:] for c in linea.split(",") if c.strip()]
    raise ErrorProveedor("Llama Guard devolvió un veredicto ilegible")


class ModeracionLlamaGuard(IModerador):
    def __init__(
        self,
        cliente: ClienteCloudflare,
        modelo_guardia: str,
        revision_infantil: ModeracionLLMSoloDesarrollo,
    ):
        self._cliente = cliente
        self._modelo = modelo_guardia
        self._infantil = revision_infantil
        self.proveedor = "cloudflare-llamaguard"
        self.timeout_s = cliente.timeout_s

    async def _guardia(self, texto: str) -> VeredictoModeracion:
        resultado = await self._cliente.run_json(
            self._modelo,
            {
                "messages": [{"role": "user", "content": texto}],
                "response_format": {"type": "json_object"},
            },
        )
        seguro, categorias = leer_veredicto_guardia(resultado.get("response"))
        uso_bruto = resultado.get("usage") or {}
        neuronas = float(uso_bruto.get("neurons") or 0.0)
        uso = Uso(
            tokens_entrada=int(uso_bruto.get("prompt_tokens") or 0),
            tokens_salida=int(uso_bruto.get("completion_tokens") or 0),
            neuronas=neuronas,
            costo_usd=self._cliente.a_usd(neuronas),
        )
        return VeredictoModeracion(seguro, [f"llamaguard:{c}" for c in categorias], uso)

    async def moderar(self, texto: str) -> VeredictoModeracion:
        # Las dos a la vez; si una lanza, gather propaga y el cuento no se aprueba.
        guardia, infantil = await asyncio.gather(
            self._guardia(texto), self._infantil.moderar(texto)
        )
        a, b = guardia.uso, infantil.uso
        uso = Uso(
            tokens_entrada=a.tokens_entrada + b.tokens_entrada,
            tokens_salida=a.tokens_salida + b.tokens_salida,
            neuronas=a.neuronas + b.neuronas,
            costo_usd=(a.costo_usd or 0.0) + (b.costo_usd or 0.0),
        )
        return VeredictoModeracion(
            guardia.aprobado and infantil.aprobado,
            guardia.categorias + infantil.categorias,
            uso,
        )
