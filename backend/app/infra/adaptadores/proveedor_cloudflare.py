"""Adaptadores de Cloudflare Workers AI (REST): visión, texto e imagen.

`POST https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{modelo}`
con `Authorization: Bearer {CLOUDFLARE_API_TOKEN}`. La respuesta viene envuelta en
`{"success", "errors", "result"}`. Cada modelo se elige por variable de entorno.

Workers AI factura en neuronas (10.000 gratis al día). Cada adaptador estima las neuronas
de su llamada con las tarifas publicadas del modelo (configurables) y las convierte a USD
con `CLOUDFLARE_USD_POR_MIL_NEURONAS`, para el costo por cuento del panel de operación.
"""

from __future__ import annotations

import base64
import binascii
import io
import math

import httpx
from PIL import Image

from app.dominio.puertos import (
    IImagen,
    ITexto,
    IVision,
    ResultadoImagen,
    ResultadoVision,
    SolicitudCuento,
    Uso,
)
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
    prompt_fondo,
)

URL_BASE = "https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/{modelo}"


class ClienteCloudflare:
    proveedor = "cloudflare"

    def __init__(
        self,
        http: httpx.AsyncClient,
        cuenta: str,
        token: str,
        timeout_s: float,
        usd_por_mil_neuronas: float,
        neuronas_texto_mtok: tuple[float, float],
        desactivar_razonamiento: bool = True,
    ):
        self._http = http
        self._cuenta = cuenta
        self._token = token
        self.timeout_s = timeout_s
        self.usd_por_mil_neuronas = usd_por_mil_neuronas
        self._neuronas_texto_mtok = neuronas_texto_mtok
        self._desactivar_razonamiento = desactivar_razonamiento

    def a_usd(self, neuronas: float) -> float:
        return neuronas / 1000 * self.usd_por_mil_neuronas

    async def run(self, modelo: str, cuerpo: dict) -> httpx.Response:
        respuesta = await self._http.post(
            URL_BASE.format(cuenta=self._cuenta, modelo=modelo),
            json=cuerpo,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=httpx.Timeout(self.timeout_s, connect=10.0),
        )
        if respuesta.status_code >= 400:
            raise ErrorProveedor(f"Cloudflare {respuesta.status_code}: {_errores(respuesta)}")
        return respuesta

    async def run_json(self, modelo: str, cuerpo: dict) -> dict:
        respuesta = await self.run(modelo, cuerpo)
        try:
            sobre = respuesta.json()
        except ValueError as exc:
            raise ErrorProveedor("Cloudflare devolvió una respuesta que no es JSON") from exc
        if not sobre.get("success", False) or not isinstance(sobre.get("result"), dict):
            raise ErrorProveedor(f"Cloudflare sin éxito: {_errores(respuesta)}")
        return sobre["result"]

    async def chat_json(
        self,
        modelo: str,
        sistema: str,
        usuario: str,
        esquema: dict,
        *,
        imagenes: list[bytes] | None = None,
        max_tokens: int = 1024,
        neuronas_mtok: tuple[float, float] | None = None,
    ) -> tuple[dict, Uso]:
        contenido: str | list = usuario
        if imagenes:
            contenido = [{"type": "text", "text": usuario}] + [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()},
                }
                for i in imagenes
            ]
        cuerpo: dict = {
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": contenido},
            ],
            "response_format": {"type": "json_schema", "json_schema": esquema},
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if self._desactivar_razonamiento:
            cuerpo["chat_template_kwargs"] = {"enable_thinking": False}
        resultado = await self.run_json(modelo, cuerpo)

        # Dos formatos según el modelo: {"response": ...} o el de chat completions.
        if "response" in resultado:
            salida = resultado["response"]
        else:
            try:
                salida = resultado["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise ErrorProveedor("Cloudflare respondió sin texto") from exc
        uso_bruto = resultado.get("usage") or {}
        entrada = int(uso_bruto.get("prompt_tokens") or 0)
        salida_tokens = int(uso_bruto.get("completion_tokens") or 0)
        n_in, n_out = neuronas_mtok or self._neuronas_texto_mtok
        neuronas = (entrada * n_in + salida_tokens * n_out) / 1_000_000
        uso = Uso(
            tokens_entrada=entrada,
            tokens_salida=salida_tokens,
            neuronas=neuronas,
            costo_usd=self.a_usd(neuronas),
        )
        try:
            return leer_json(salida), uso
        except ValueError as exc:
            raise ErrorProveedor(f"Cloudflare devolvió algo que no es JSON: {exc}") from exc


def _errores(respuesta: httpx.Response) -> str:
    try:
        errores = respuesta.json().get("errors") or []
        return "; ".join(str(e.get("message", e)) for e in errores)[:300] or "sin detalle"
    except (ValueError, AttributeError):
        return respuesta.text[:200]


def _b64(valor: object, que: str) -> bytes:
    if not isinstance(valor, str) or not valor:
        raise ErrorProveedor(f"Cloudflare no devolvió {que}")
    try:
        return base64.b64decode(valor, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ErrorProveedor(f"{que} de Cloudflare no es base64 válido") from exc


class VisionCloudflare(IVision):
    proveedor = "cloudflare"

    def __init__(self, cliente: ClienteCloudflare, modelo: str, neuronas_mtok: tuple[float, float]):
        self._cliente = cliente
        self._modelo = modelo
        self._neuronas_mtok = neuronas_mtok
        self.timeout_s = cliente.timeout_s

    async def identificar(self, imagen_png: bytes) -> ResultadoVision:
        datos, uso = await self._cliente.chat_json(
            self._modelo,
            PROMPT_VISION,
            "¿Qué dibujó el niño? Responde en JSON.",
            ESQUEMA_VISION,
            imagenes=[imagen_png],
            max_tokens=400,
            neuronas_mtok=self._neuronas_mtok,
        )
        return ResultadoVision(hipotesis_desde(datos), uso, atributos_desde(datos))


class TextoCloudflare(ITexto):
    proveedor = "cloudflare"

    def __init__(self, cliente: ClienteCloudflare, modelo: str, max_tokens: int = 1500):
        self._cliente = cliente
        self._modelo = modelo
        self._max_tokens = max_tokens
        self.timeout_s = cliente.timeout_s

    async def escribir_cuento(self, solicitud: SolicitudCuento):
        datos, uso = await self._cliente.chat_json(
            self._modelo,
            mensaje_solicitud(solicitud),
            f"Protagonista: {solicitud.personaje}",
            ESQUEMA_CUENTO,
            max_tokens=self._max_tokens,
        )
        return cuento_desde(datos, uso)


class ImagenCloudflare(IImagen):
    """FLUX.1 [schnell]: devuelve `{"image": base64}` (JPEG). Se convierte a PNG.

    Neuronas = teselas de 512x512 de la salida x tarifa por tesela + pasos x tarifa por paso.
    """

    proveedor = "cloudflare"

    def __init__(
        self,
        cliente: ClienteCloudflare,
        modelo: str,
        pasos: int,
        neuronas_tesela: float,
        neuronas_paso: float,
    ):
        self._cliente = cliente
        self._modelo = modelo
        self._pasos = pasos
        self._neuronas_tesela = neuronas_tesela
        self._neuronas_paso = neuronas_paso
        self.timeout_s = cliente.timeout_s

    async def generar_fondo(self, descripcion: str) -> ResultadoImagen:
        resultado = await self._cliente.run_json(
            self._modelo, {"prompt": prompt_fondo(descripcion)[:2048], "steps": self._pasos}
        )
        crudo = _b64(resultado.get("image"), "la imagen")
        try:
            with Image.open(io.BytesIO(crudo)) as img:
                ancho, alto = img.size
                salida = io.BytesIO()
                img.convert("RGB").save(salida, format="PNG")
        except OSError as exc:
            raise ErrorProveedor("la imagen de Cloudflare no se puede abrir") from exc
        teselas = math.ceil(ancho / 512) * math.ceil(alto / 512)
        neuronas = teselas * self._neuronas_tesela + self._pasos * self._neuronas_paso
        uso = Uso(imagenes=1, neuronas=neuronas, costo_usd=self._cliente.a_usd(neuronas))
        return ResultadoImagen(salida.getvalue(), uso)
