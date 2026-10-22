"""Adaptador de voz: ElevenLabs Text-to-Speech (Flash / Turbo v2.5)."""

from __future__ import annotations

import httpx

from app.dominio.puertos import IVoz, ResultadoAudio, Uso

_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voz}"


class VozElevenLabs(IVoz):
    proveedor = "elevenlabs"

    def __init__(self, cliente: httpx.AsyncClient, api_key: str, voz_id: str, modelo: str):
        self._cliente = cliente
        self._api_key = api_key
        self._voz_id = voz_id
        self._modelo = modelo

    async def narrar(self, texto: str) -> ResultadoAudio:
        respuesta = await self._cliente.post(
            _URL.format(voz=self._voz_id),
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self._api_key, "accept": "audio/mpeg"},
            json={"text": texto, "model_id": self._modelo, "language_code": "es"},
        )
        respuesta.raise_for_status()
        if not respuesta.content:
            raise RuntimeError("ElevenLabs devolvió un audio vacío")
        return ResultadoAudio(respuesta.content, Uso(caracteres=len(texto)))
