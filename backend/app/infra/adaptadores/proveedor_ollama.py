"""Adaptadores de Ollama (API nativa `/api/chat`): visión y texto, para la prueba local.

Ollama corre en el host y no cobra: el costo de cada llamada es 0. Por CPU va a pocos
tokens por segundo, así que el timeout es propio (`OLLAMA_TIMEOUT_S`) y el orquestador lo
respeta en vez del global. Ollama no genera imágenes: con `PROVEEDOR_IMAGEN=ninguno` el paso
de escenarios usa un fondo del banco.
"""

from __future__ import annotations

import base64

import httpx

from app.dominio.puertos import ITexto, IVision, ResultadoVision, SolicitudCuento, Uso
from app.infra.adaptadores.comun import (
    ESQUEMA_CUENTO,
    ESQUEMA_VISION,
    PROMPT_VISION,
    ErrorProveedor,
    atributos_desde,
    cuento_desde,
    hipotesis_desde,
    leer_json,
    mensaje_solicitud,
)


class ClienteOllama:
    """Cliente mínimo de `/api/chat` con salida estructurada (`format` = esquema JSON)."""

    proveedor = "ollama"

    def __init__(self, http: httpx.AsyncClient, url: str, timeout_s: float):
        self._http = http
        self._url = url.rstrip("/")
        self.timeout_s = timeout_s

    async def chat_json(
        self,
        modelo: str,
        sistema: str,
        usuario: str,
        esquema: dict,
        *,
        imagenes: list[bytes] | None = None,
        max_tokens: int = 1024,
        neuronas_mtok: tuple[float, float] | None = None,  # no aplica: Ollama no cobra
    ) -> tuple[dict, Uso]:
        mensaje: dict = {"role": "user", "content": usuario}
        if imagenes:
            mensaje["images"] = [base64.b64encode(i).decode() for i in imagenes]
        cuerpo = {
            "model": modelo,
            "messages": [{"role": "system", "content": sistema}, mensaje],
            "stream": False,
            "format": esquema["schema"],
            "options": {"temperature": 0.7, "num_predict": max_tokens},
        }
        respuesta = await self._http.post(
            f"{self._url}/api/chat",
            json=cuerpo,
            timeout=httpx.Timeout(self.timeout_s, connect=10.0),
        )
        if respuesta.status_code >= 400:
            try:
                detalle = respuesta.json().get("error", "")
            except ValueError:
                detalle = respuesta.text[:200]
            raise ErrorProveedor(f"Ollama {respuesta.status_code}: {detalle}")
        datos = respuesta.json()
        contenido = (datos.get("message") or {}).get("content", "")
        uso = Uso(
            tokens_entrada=int(datos.get("prompt_eval_count") or 0),
            tokens_salida=int(datos.get("eval_count") or 0),
            costo_usd=0.0,
        )
        try:
            return leer_json(contenido), uso
        except ValueError as exc:
            raise ErrorProveedor(f"Ollama devolvió algo que no es JSON: {exc}") from exc


class VisionOllama(IVision):
    """Necesita un modelo con visión descargado (`OLLAMA_MODELO_VISION`). Si no está,
    Ollama responde 404, el paso se degrada y la app pasa a la identificación asistida."""

    proveedor = "ollama"

    def __init__(self, cliente: ClienteOllama, modelo: str):
        self._cliente = cliente
        self._modelo = modelo
        self.timeout_s = cliente.timeout_s

    async def identificar(self, imagen_png: bytes) -> ResultadoVision:
        datos, uso = await self._cliente.chat_json(
            self._modelo,
            PROMPT_VISION,
            "¿Qué dibujó el niño? Responde en JSON.",
            ESQUEMA_VISION,
            imagenes=[imagen_png],
            max_tokens=400,
        )
        return ResultadoVision(hipotesis_desde(datos), uso, atributos_desde(datos))


class TextoOllama(ITexto):
    proveedor = "ollama"

    def __init__(self, cliente: ClienteOllama, modelo: str, max_tokens: int = 1200):
        self._cliente = cliente
        self._modelo = modelo
        self._max_tokens = max_tokens
        self.timeout_s = cliente.timeout_s

    async def escribir_cuento(self, solicitud: SolicitudCuento):
        datos, uso = await self._cliente.chat_json(
            self._modelo,
            mensaje_solicitud(solicitud),
            f"Protagonista: {solicitud.personaje}. Responde en JSON con «titulo» y «paginas».",
            ESQUEMA_CUENTO,
            max_tokens=self._max_tokens,
        )
        return cuento_desde(datos, uso)
