"""Adaptadores de Cloudflare Workers AI (REST): visión, texto, imagen y voz.

`POST https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{modelo}`
con `Authorization: Bearer {CLOUDFLARE_API_TOKEN}`. La respuesta viene envuelta en
`{"success", "errors", "result"}`. Cada modelo se elige por variable de entorno.

Workers AI factura en neuronas (10.000 gratis al día). Cada adaptador estima las neuronas
de su llamada con las tarifas publicadas del modelo (configurables) y las convierte a USD
con `CLOUDFLARE_USD_POR_MIL_NEURONAS`, para el costo por cuento del panel de operación.

Rotación de cuentas: el cliente puede tener varias cuentas en orden (la 1 es
`CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN`; las extra, `..._2`, `..._3`...). Ante un 429
por cupo diario marca la cuenta agotada hasta la próxima 00:00 UTC y repite la misma petición
con la siguiente; ante un 429 de ritmo la aparta un minuto, sin darla por agotada. Si no queda
ninguna, lanza `CupoAgotadoCloudflare` como siempre. Nada de esto se ve fuera del backend.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import logging
import math
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import httpx
from PIL import Image

from app.dominio.puertos import (
    CupoAgotado,
    IImagen,
    ITexto,
    IVision,
    IVoz,
    ResultadoAudio,
    ResultadoImagen,
    ResultadoVision,
    SolicitudCuento,
    Uso,
)
from app.infra.adaptadores.audio import es_wav, segundos_mp3, texto_para_narrar, wav_a_mp3
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

# Solo si el audio no viene en WAV y no se puede medir: unos 15 caracteres por segundo de habla.
CARACTERES_POR_SEGUNDO = 15

URL_BASE = "https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/{modelo}"

MODELO_VOZ_AURA = "@cf/deepgram/aura-2-es"
MODELO_VOZ_MELOTTS = "@cf/myshell-ai/melotts"


class CupoAgotadoCloudflare(ErrorProveedor, CupoAgotado):
    """429 de Workers AI: error del proveedor y, para el orquestador, cupo agotado."""

    def __init__(self, mensaje: str, diario: bool = False):
        CupoAgotado.__init__(self, mensaje, diario)


log = logging.getLogger(__name__)

# 429 de ritmo (peticiones por minuto, por cuenta): la cuenta se aparta este tiempo, o el
# que pida `Retry-After`, con este techo. No se da por agotada: su cupo diario sigue ahí.
ESPERA_RITMO_S = 60.0
ESPERA_RITMO_MAX_S = 300.0
# El cupo puede no reponerse a las 00:00 UTC (el 2026-11-10 seguía en 429 pasadas las 00:25,
# y hay reportes de una ventana móvil de ~24 h). Si una cuenta agotada ayer vuelve a dar 429
# diario hoy, se vuelve a probar cada media hora en vez de apartarla otro día entero.
REPRUEBA_TRAS_REPOSICION = timedelta(minutes=30)


@dataclass(frozen=True)
class CuentaCloudflare:
    """Una cuenta de Workers AI. Ni el id ni el token salen en `repr` ni en los logs."""

    id: str = field(repr=False)
    token: str = field(repr=False)


class _EstadoCuenta:
    """Estado en memoria de una cuenta. Solo se toca con el candado del cliente."""

    __slots__ = ("agotada_desde", "agotada_hasta", "ritmo_hasta")

    def __init__(self) -> None:
        self.agotada_hasta: datetime | None = None  # cupo diario: apartada hasta aquí
        self.agotada_desde: date | None = None  # día UTC del primer 429 diario de la racha
        self.ritmo_hasta: datetime | None = None  # límite de ritmo: apartada hasta aquí


def _ahora_utc() -> datetime:
    return datetime.now(UTC)


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
        *,
        cuentas_extra: Sequence[CuentaCloudflare] = (),
        reloj: Callable[[], datetime] = _ahora_utc,
    ):
        self._http = http
        # Orden de uso: la cuenta 1 (CLOUDFLARE_ACCOUNT_ID) y luego las extra (_2, _3...)
        self._cuentas = [CuentaCloudflare(cuenta, token), *cuentas_extra]
        self._estados = [_EstadoCuenta() for _ in self._cuentas]
        # Las secciones con candado son cortas y sin `await`: dos cuentos a la vez (o un
        # hilo de `to_thread`) no pueden dejar el estado a medias.
        self._candado = threading.Lock()
        self._reloj = reloj
        self.timeout_s = timeout_s
        self.usd_por_mil_neuronas = usd_por_mil_neuronas
        self._neuronas_texto_mtok = neuronas_texto_mtok
        self._desactivar_razonamiento = desactivar_razonamiento

    def a_usd(self, neuronas: float) -> float:
        return neuronas / 1000 * self.usd_por_mil_neuronas

    @property
    def total_cuentas(self) -> int:
        return len(self._cuentas)

    def _nombre(self, i: int) -> str:
        return f"cuenta {i + 1} de {len(self._cuentas)}"

    async def run(self, modelo: str, cuerpo: dict) -> httpx.Response:
        # Cada cuenta se prueba como mucho una vez por petición, en orden.
        probadas: set[int] = set()
        ultimo_429: CupoAgotadoCloudflare | None = None
        while True:
            i = self._elegir(probadas)
            if i is None:
                if ultimo_429 is not None:
                    raise ultimo_429
                # Todas apartadas por cupo diario: el mismo error de siempre, sin llamar.
                raise CupoAgotadoCloudflare(
                    "Cloudflare 429: todas las cuentas sin cupo diario", diario=True
                )
            if probadas:
                log.info(
                    "Cloudflare: se repite la petición (%s) con la %s", modelo, self._nombre(i)
                )
            probadas.add(i)
            respuesta = await self._post(self._cuentas[i], modelo, cuerpo)
            if respuesta.status_code == 429:
                # Sin cupo: el diario (10.000 neuronas gratis, vuelve hacia las 00:00 UTC) o
                # un límite de ritmo. Se pasa a la siguiente cuenta; si no queda ninguna, el
                # orquestador no reintenta y el cuento sigue sin esa capacidad.
                detalle = _errores(respuesta)
                diario = any(p in detalle.lower() for p in ("daily", "allocation", "neurons"))
                ultimo_429 = CupoAgotadoCloudflare(f"Cloudflare 429: {detalle}", diario=diario)
                if diario:
                    self._marcar_agotada(i)
                else:
                    self._marcar_ritmo(i, respuesta)
                continue
            if respuesta.status_code >= 400:
                raise ErrorProveedor(f"Cloudflare {respuesta.status_code}: {_errores(respuesta)}")
            self._exito(i)
            return respuesta

    async def _post(self, cuenta: CuentaCloudflare, modelo: str, cuerpo: dict) -> httpx.Response:
        # El tope de httpx es por lectura: un cuerpo que llega a goteo nunca lo agota. El
        # tope de la llamada entera lo pone el orquestador (`wait_for` con `timeout_s`).
        try:
            return await self._http.post(
                URL_BASE.format(cuenta=cuenta.id, modelo=modelo),
                json=cuerpo,
                headers={"Authorization": f"Bearer {cuenta.token}"},
                timeout=httpx.Timeout(self.timeout_s, connect=10.0),
            )
        except httpx.TimeoutException as exc:
            # Mismo trato que el tope del orquestador: un reintento y luego falla limpio.
            # Un timeout no es falta de cupo: no se cambia de cuenta.
            raise TimeoutError(f"Cloudflare no respondió a tiempo ({modelo})") from exc

    def _elegir(self, probadas: set[int]) -> int | None:
        """La primera cuenta libre no probada; si no hay, una apartada solo por ritmo."""
        ahora = self._reloj()
        repuestas: list[int] = []
        elegida: int | None = None
        de_reserva: int | None = None
        with self._candado:
            for i, estado in enumerate(self._estados):
                if estado.agotada_hasta is not None:
                    if ahora < estado.agotada_hasta:
                        continue
                    estado.agotada_hasta = None  # cambió el día UTC (o toca reprobar)
                    repuestas.append(i)
                if i in probadas:
                    continue
                if estado.ritmo_hasta is not None and ahora < estado.ritmo_hasta:
                    if de_reserva is None:
                        de_reserva = i
                    continue
                if elegida is None:
                    elegida = i
        for i in repuestas:
            log.info("Cloudflare: la %s vuelve a estar disponible", self._nombre(i))
        # Con una sola cuenta esto es lo de siempre: tras un 429 de ritmo se sigue llamando.
        return elegida if elegida is not None else de_reserva

    def _marcar_agotada(self, i: int) -> None:
        ahora = self._reloj()
        hoy = ahora.date()
        medianoche = datetime.combine(hoy + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        with self._candado:
            estado = self._estados[i]
            if estado.agotada_hasta is not None and ahora < estado.agotada_hasta:
                return  # otra petición en curso ya la marcó
            if estado.agotada_desde == hoy - timedelta(days=1):
                hasta = min(ahora + REPRUEBA_TRAS_REPOSICION, medianoche)
            else:
                estado.agotada_desde = hoy
                hasta = medianoche
            estado.agotada_hasta = hasta
        log.warning(
            "Cloudflare: cupo diario agotado en la %s; apartada hasta las %s UTC",
            self._nombre(i),
            hasta.strftime("%H:%M"),
        )

    def _marcar_ritmo(self, i: int, respuesta: httpx.Response) -> None:
        try:
            espera = float(respuesta.headers.get("retry-after", ""))
        except ValueError:
            espera = ESPERA_RITMO_S
        espera = min(max(espera, 1.0), ESPERA_RITMO_MAX_S)
        hasta = self._reloj() + timedelta(seconds=espera)
        with self._candado:
            estado = self._estados[i]
            if estado.ritmo_hasta is None or estado.ritmo_hasta < hasta:
                estado.ritmo_hasta = hasta
        log.warning(
            "Cloudflare: límite de ritmo en la %s; se aparta %.0f s", self._nombre(i), espera
        )

    def _exito(self, i: int) -> None:
        with self._candado:
            estado = self._estados[i]
            estado.ritmo_hasta = None
            if estado.agotada_hasta is None:
                estado.agotada_desde = None  # la racha de cupo agotado terminó

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
        # Decodificar y recodificar es CPU de Pillow: en un hilo, fuera del bucle de eventos.
        png, (ancho, alto) = await asyncio.to_thread(_jpeg_a_png, crudo)
        teselas = math.ceil(ancho / 512) * math.ceil(alto / 512)
        neuronas = teselas * self._neuronas_tesela + self._pasos * self._neuronas_paso
        uso = Uso(imagenes=1, neuronas=neuronas, costo_usd=self._cliente.a_usd(neuronas))
        return ResultadoImagen(png, uso)


def _jpeg_a_png(crudo: bytes) -> tuple[bytes, tuple[int, int]]:
    try:
        with Image.open(io.BytesIO(crudo)) as img:
            tamano = img.size
            salida = io.BytesIO()
            img.convert("RGB").save(salida, format="PNG")
    except OSError as exc:
        raise ErrorProveedor("la imagen de Cloudflare no se puede abrir") from exc
    return salida.getvalue(), tamano


class VozCloudflare(IVoz):
    """MeloTTS: `{"prompt", "lang"}` -> `{"audio": base64}`; hoy llega como WAV y se pasa a MP3.

    Las neuronas se cobran por minuto de audio (18,63 por minuto con la tarifa publicada),
    así que se calculan con la duración real del WAV y no con el largo del texto.
    """

    proveedor = "cloudflare"

    def __init__(
        self, cliente: ClienteCloudflare, modelo: str, idioma: str, neuronas_minuto: float
    ):
        self._cliente = cliente
        self._modelo = modelo
        self._idioma = idioma
        self._neuronas_minuto = neuronas_minuto
        self.timeout_s = cliente.timeout_s

    async def narrar(self, texto: str) -> ResultadoAudio:
        texto = texto_para_narrar(texto)
        resultado = await self._cliente.run_json(
            self._modelo, {"prompt": texto, "lang": self._idioma}
        )
        crudo = _b64(resultado.get("audio"), "el audio")
        if es_wav(crudo):
            mp3, segundos = wav_a_mp3(crudo)
        else:
            # Si algún día Cloudflare devuelve ya MP3, se entrega tal cual.
            mp3, segundos = crudo, len(texto) / CARACTERES_POR_SEGUNDO
        if not mp3:
            raise ErrorProveedor("Cloudflare devolvió un audio vacío")
        neuronas = segundos / 60 * self._neuronas_minuto
        uso = Uso(caracteres=len(texto), neuronas=neuronas, costo_usd=self._cliente.a_usd(neuronas))
        return ResultadoAudio(mp3, uso)


class VozCloudflareAura(IVoz):
    """Deepgram Aura-2 en español (`@cf/deepgram/aura-2-es`), voz «javier» por defecto.

    `{"text", "speaker", "encoding": "mp3"}` -> el MP3 crudo (`audio/mpeg`, mono, 24 kHz,
    48 kbps): ya es ligero y se entrega tal cual, porque recodificarlo solo perdería calidad.
    Aura-2 pone el ritmo y la entonación según el texto, así que se le pasa limpio y bien
    puntuado (`texto_para_narrar`).

    Se cobra por carácter (US$0,03 por 1.000). Cloudflare informa las neuronas reales en la
    cabecera `cf-ai-neurons`; si no viene, se estiman con la tarifa.
    """

    proveedor = "cloudflare"

    def __init__(
        self,
        cliente: ClienteCloudflare,
        modelo: str,
        voz: str,
        neuronas_mil_caracteres: float,
    ):
        self._cliente = cliente
        self._modelo = modelo
        self._voz = voz
        self._neuronas_mil_caracteres = neuronas_mil_caracteres
        self.timeout_s = cliente.timeout_s

    async def narrar(self, texto: str) -> ResultadoAudio:
        texto = texto_para_narrar(texto)
        if not texto:
            raise ErrorProveedor("no hay texto que narrar")
        respuesta = await self._cliente.run(
            self._modelo, {"text": texto, "speaker": self._voz, "encoding": "mp3"}
        )
        tipo = respuesta.headers.get("content-type", "")
        if "json" in tipo:
            # Por si la API REST algún día lo envuelve como MeloTTS: {"result": {"audio": b64}}
            try:
                sobre = respuesta.json()
            except ValueError as exc:
                raise ErrorProveedor("Cloudflare devolvió una respuesta que no es JSON") from exc
            resultado = sobre.get("result") if isinstance(sobre, dict) else None
            mp3 = _b64((resultado or {}).get("audio"), "el audio")
        else:
            mp3 = respuesta.content
        if not mp3 or segundos_mp3(mp3) <= 0:
            raise ErrorProveedor("Cloudflare devolvió un audio vacío o que no es MP3")
        neuronas = _neuronas_de(respuesta) or (len(texto) / 1000 * self._neuronas_mil_caracteres)
        uso = Uso(caracteres=len(texto), neuronas=neuronas, costo_usd=self._cliente.a_usd(neuronas))
        return ResultadoAudio(mp3, uso)


def _neuronas_de(respuesta: httpx.Response) -> float:
    try:
        return max(0.0, float(respuesta.headers.get("cf-ai-neurons", "")))
    except ValueError:
        return 0.0
