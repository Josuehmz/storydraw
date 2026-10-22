"""Moderación con un LLM genérico (Ollama o Cloudflare Workers AI).

⚠ SOLO PARA DESARROLLO. Existe para que la prueba local funcione sin claves. Un LLM
pequeño no es un clasificador de seguridad: en producción la configuración la rechaza y se
usa la moderación de OpenAI (`PROVEEDOR_MODERACION=openai`, gratuita con clave).

Falla cerrada: si el LLM no responde, tarda más del timeout, devuelve algo ilegible o no
trae el campo «apto», se lanza una excepción y el orquestador trata el cuento como no
aprobado (el niño no ve nada). Solo `"apto": true` (booleano) aprueba.
"""

from __future__ import annotations

from app.dominio.puertos import IModerador, VeredictoModeracion
from app.infra.adaptadores.comun import (
    ESQUEMA_MODERACION,
    PROMPT_MODERACION,
    MotorChatJSON,
    veredicto_desde,
)


class ModeracionLLMSoloDesarrollo(IModerador):
    def __init__(self, motor: MotorChatJSON, modelo: str):
        self._motor = motor
        self._modelo = modelo
        self.proveedor = f"{motor.proveedor}-llm-dev"
        self.timeout_s = motor.timeout_s

    async def moderar(self, texto: str) -> VeredictoModeracion:
        datos, uso = await self._motor.chat_json(
            self._modelo,
            PROMPT_MODERACION,
            f"Texto a revisar:\n<<<\n{texto}\n>>>",
            ESQUEMA_MODERACION,
            max_tokens=150,
        )
        aprobado, categorias = veredicto_desde(datos)  # lanza si falta «apto»
        return VeredictoModeracion(aprobado, [f"llm:{c}" for c in categorias], uso)
