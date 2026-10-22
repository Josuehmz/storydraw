"""Orquestador del pipeline: asyncio, cinco pasos, reintento por paso y degradación.

Pasos: 1 identificar (visión, opcional) · 2 escribir (texto) · 3 moderar (obligatorio) ·
4 escenarios (imagen) · 5 narrar (voz). Después, la composición monta las páginas y las
sube al almacén.

- Cada paso se reintenta por separado; un fallo no rehace el cuento entero.
- Sin visión, se usa lo que el niño escribió (o un personaje genérico).
- Sin imagen, se usa un fondo del banco. Sin voz, el cuento se entrega escrito con aviso.
- Sin cuento o sin moderación aprobada, no hay nada que mostrar: el niño no ve nada.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, TypeVar

from app.dominio.composicion import Compositor, fondo_del_banco
from app.dominio.costos import Capacidad, Tarifario
from app.dominio.moderacion import Moderacion
from app.dominio.puertos import (
    CuentoTexto,
    Hipotesis,
    IAlmacen,
    IImagen,
    ITexto,
    IVision,
    IVoz,
    SolicitudCuento,
    Uso,
)

log = logging.getLogger(__name__)
T = TypeVar("T")

PERSONAJE_GENERICO = "un amigo mágico"
AVISO_SIN_ESCENARIOS = "sin_escenarios"
AVISO_SIN_NARRACION = "sin_narracion"
AVISO_SIN_IDENTIFICACION = "sin_identificacion"

Estado = Literal["listo", "rechazado", "fallido"]


class FalloPaso(Exception):
    def __init__(self, paso: str, causa: BaseException):
        super().__init__(f"{paso}: {type(causa).__name__}")
        self.paso = paso
        self.causa = causa


@dataclass
class MetricaPaso:
    paso: str
    proveedor: str
    estado: Literal["ok", "degradado", "fallido", "omitido", "rechazado"] = "ok"
    intentos: int = 0
    latencia_ms: int = 0
    costo_usd: float = 0.0

    def como_dict(self) -> dict:
        return {
            "paso": self.paso,
            "proveedor": self.proveedor,
            "estado": self.estado,
            "intentos": self.intentos,
            "latencia_ms": self.latencia_ms,
            "costo_usd": round(self.costo_usd, 6),
        }


@dataclass
class Rechazo:
    origen: Literal["entrada", "cuento"]
    texto: str
    categorias: list[str]


@dataclass
class PaginaFinal:
    numero: int
    texto: str
    imagen_clave: str
    audio_clave: str | None


@dataclass
class ResultadoIdentificacion:
    disponible: bool
    hipotesis: list[Hipotesis]
    metrica: MetricaPaso


@dataclass
class ResultadoCuento:
    estado: Estado
    titulo: str | None = None
    personaje: str | None = None
    paginas: list[PaginaFinal] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    pasos: list[MetricaPaso] = field(default_factory=list)
    rechazos: list[Rechazo] = field(default_factory=list)
    latencia_ms: int = 0

    @property
    def costo_usd(self) -> float:
        return round(sum(p.costo_usd for p in self.pasos), 6)


def clave_imagen(cuento_id: str, numero: int) -> str:
    return f"cuentos/{cuento_id}/paginas/{numero}.png"


def clave_audio(cuento_id: str, numero: int) -> str:
    return f"cuentos/{cuento_id}/audio/{numero}.mp3"


class Orquestador:
    def __init__(
        self,
        *,
        vision: IVision,
        texto: ITexto,
        imagen: IImagen,
        voz: IVoz,
        moderacion: Moderacion,
        compositor: Compositor,
        almacen: IAlmacen,
        tarifario: Tarifario,
        reintentos: int = 2,
        espera_base_s: float = 0.5,
        max_regeneraciones: int = 2,
        timeout_s: float = 60.0,
    ):
        self.vision = vision
        self.texto = texto
        self.imagen = imagen
        self.voz = voz
        self.moderacion = moderacion
        self.compositor = compositor
        self.almacen = almacen
        self.tarifario = tarifario
        self.reintentos = reintentos
        self.espera_base_s = espera_base_s
        self.max_regeneraciones = max_regeneraciones
        self.timeout_s = timeout_s

    # ---------------------------------------------------------------- utilidades

    async def _con_reintentos(
        self,
        metrica: MetricaPaso,
        capacidad: Capacidad,
        llamada: Callable[[], Awaitable[T]],
        uso_de: Callable[[T], Uso],
        timeout_s: float | None = None,
    ) -> T:
        """Ejecuta una llamada con reintentos; acumula intentos, latencia y costo.

        `timeout_s` es el del adaptador (Ollama por CPU tarda minutos); si no trae, el global.
        """
        limite = timeout_s or self.timeout_s
        ultimo: BaseException | None = None
        inicio = time.perf_counter()
        try:
            for intento in range(self.reintentos + 1):
                metrica.intentos += 1
                try:
                    resultado = await asyncio.wait_for(llamada(), timeout=limite)
                except Exception as exc:
                    ultimo = exc
                    log.warning(
                        "paso=%s proveedor=%s intento=%d error=%s",
                        metrica.paso,
                        metrica.proveedor,
                        intento + 1,
                        type(exc).__name__,
                    )
                    if intento < self.reintentos and self.espera_base_s:
                        await asyncio.sleep(self.espera_base_s * (2**intento))
                    continue
                metrica.costo_usd += self.tarifario.costo(capacidad, uso_de(resultado))
                return resultado
        finally:
            metrica.latencia_ms += int((time.perf_counter() - inicio) * 1000)
        assert ultimo is not None  # noqa: S101 - solo se llega aquí tras fallar
        raise FalloPaso(metrica.paso, ultimo)

    # ---------------------------------------------------------------- paso 1

    async def identificar(self, dibujo_png: bytes) -> ResultadoIdentificacion:
        metrica = MetricaPaso("identificar", self.vision.proveedor)
        try:
            res = await self._con_reintentos(
                metrica,
                "vision",
                lambda: self.vision.identificar(dibujo_png),
                lambda r: r.uso,
                self.vision.timeout_s,
            )
        except FalloPaso:
            metrica.estado = "degradado"
            return ResultadoIdentificacion(False, [], metrica)
        hipotesis = sorted(res.hipotesis, key=lambda h: h.confianza, reverse=True)[:4]
        hipotesis = [
            Hipotesis(h.etiqueta.strip()[:60], max(0.0, min(1.0, h.confianza)))
            for h in hipotesis
            if h.etiqueta.strip()
        ]
        # Lo que propone la visión también se modera antes de mostrárselo al niño.
        hipotesis = [h for h in hipotesis if self.moderacion.revisar_local(h.etiqueta).aprobado]
        return ResultadoIdentificacion(bool(hipotesis), hipotesis, metrica)

    # ---------------------------------------------------------------- pipeline

    async def crear_cuento(
        self, cuento_id: str, dibujo_png: bytes, personaje: str | None, edad: int
    ) -> ResultadoCuento:
        inicio = time.perf_counter()
        resultado = ResultadoCuento(estado="fallido")
        try:
            await self._pipeline(resultado, cuento_id, dibujo_png, personaje, edad)
        finally:
            resultado.latencia_ms = int((time.perf_counter() - inicio) * 1000)
        return resultado

    async def _pipeline(
        self,
        resultado: ResultadoCuento,
        cuento_id: str,
        dibujo_png: bytes,
        personaje: str | None,
        edad: int,
    ) -> None:
        # Recorte en un hilo: es CPU y no debe bloquear el bucle de eventos.
        recorte_tarea = asyncio.create_task(asyncio.to_thread(self.compositor.recortar, dibujo_png))

        # Paso 1 · identificar (opcional: si el niño ya eligió o escribió, se omite)
        personaje = (personaje or "").strip()[:120]
        if personaje:
            resultado.pasos.append(MetricaPaso("identificar", self.vision.proveedor, "omitido"))
        else:
            ident = await self.identificar(dibujo_png)
            resultado.pasos.append(ident.metrica)
            if ident.disponible:
                personaje = ident.hipotesis[0].etiqueta
            else:
                personaje = PERSONAJE_GENERICO
                resultado.avisos.append(AVISO_SIN_IDENTIFICACION)
        resultado.personaje = personaje

        # Pasos 2 y 3 · escribir y moderar, con regeneración si se rechaza
        m_escribir = MetricaPaso("escribir", self.texto.proveedor)
        m_moderar = MetricaPaso("moderar", self.moderacion.proveedor)
        resultado.pasos += [m_escribir, m_moderar]

        if not await self._moderar(m_moderar, resultado, "entrada", personaje):
            m_escribir.estado = "omitido"
            resultado.estado = "rechazado"
            recorte_tarea.cancel()
            return

        cuento: CuentoTexto | None = None
        incompletos = 0
        for _ in range(self.max_regeneraciones + 1):
            try:
                candidato = await self._con_reintentos(
                    m_escribir,
                    "texto",
                    lambda: self.texto.escribir_cuento(SolicitudCuento(personaje, edad)),
                    lambda r: r.uso,
                    self.texto.timeout_s,
                )
            except FalloPaso:
                m_escribir.estado = "fallido"
                resultado.estado = "fallido"
                recorte_tarea.cancel()
                return
            if len(candidato.paginas) < 3:
                incompletos += 1
                continue
            completo = candidato.titulo + "\n" + "\n".join(p.texto for p in candidato.paginas)
            if await self._moderar(m_moderar, resultado, "cuento", completo):
                cuento = candidato
                break
        if cuento is None:
            sin_moderar = incompletos == self.max_regeneraciones + 1
            resultado.estado = "fallido" if sin_moderar else "rechazado"
            recorte_tarea.cancel()
            return

        paginas = cuento.paginas[:3]
        resultado.titulo = cuento.titulo.strip()[:200]

        # Pasos 4 y 5 · escenarios y narración en paralelo; ninguno bloquea al otro
        m_escenarios = MetricaPaso("escenarios", self.imagen.proveedor)
        m_narrar = MetricaPaso("narrar", self.voz.proveedor)
        resultado.pasos += [m_escenarios, m_narrar]
        fondos, audios = await asyncio.gather(
            self._escenarios(m_escenarios, [p.escena for p in paginas]),
            self.narrar([p.texto for p in paginas], m_narrar),
        )
        if m_escenarios.estado == "degradado":
            resultado.avisos.append(AVISO_SIN_ESCENARIOS)
        if m_narrar.estado == "degradado":
            resultado.avisos.append(AVISO_SIN_NARRACION)

        # Composición y subida al almacén
        recorte = await recorte_tarea
        for i, pagina in enumerate(paginas, start=1):
            png = await asyncio.to_thread(self.compositor.componer, fondos[i - 1], recorte, i)
            await self.almacen.guardar(clave_imagen(cuento_id, i), png, "image/png")
            audio_clave = None
            if audios[i - 1] is not None:
                audio_clave = clave_audio(cuento_id, i)
                await self.almacen.guardar(audio_clave, audios[i - 1], "audio/mpeg")
            resultado.paginas.append(
                PaginaFinal(i, pagina.texto.strip(), clave_imagen(cuento_id, i), audio_clave)
            )
        resultado.estado = "listo"

    async def _moderar(
        self,
        metrica: MetricaPaso,
        resultado: ResultadoCuento,
        origen: Literal["entrada", "cuento"],
        texto: str,
    ) -> bool:
        try:
            veredicto = await self._con_reintentos(
                metrica,
                "moderacion",
                lambda: self.moderacion.revisar(texto),
                lambda r: r.uso,
                self.moderacion.timeout_s,
            )
        except FalloPaso:
            # Falla cerrada: sin moderación no se muestra nada.
            metrica.estado = "fallido"
            resultado.rechazos.append(Rechazo(origen, texto, ["moderacion_no_disponible"]))
            return False
        if not veredicto.aprobado:
            metrica.estado = "rechazado"
            resultado.rechazos.append(Rechazo(origen, texto, veredicto.categorias))
            return False
        metrica.estado = "ok"
        return True

    async def _escenarios(self, metrica: MetricaPaso, escenas: list[str]) -> list[bytes]:
        inicio = time.perf_counter()

        async def uno(i: int, escena: str) -> bytes:
            try:
                res = await self._con_reintentos(
                    metrica,
                    "imagen",
                    lambda: self.imagen.generar_fondo(escena),
                    lambda r: r.uso,
                    self.imagen.timeout_s,
                )
                return res.png
            except FalloPaso:
                metrica.estado = "degradado"
                return fondo_del_banco(i)

        fondos = list(await asyncio.gather(*(uno(i, e) for i, e in enumerate(escenas))))
        metrica.latencia_ms = int((time.perf_counter() - inicio) * 1000)  # tiempo de pared
        return fondos

    async def narrar(
        self, textos: list[str], metrica: MetricaPaso | None = None
    ) -> list[bytes | None]:
        """Paso 5. Público porque la app puede pedir reintentar solo la narración."""
        metrica = metrica or MetricaPaso("narrar", self.voz.proveedor)
        inicio = time.perf_counter()

        async def uno(texto: str) -> bytes | None:
            try:
                res = await self._con_reintentos(
                    metrica,
                    "voz",
                    lambda: self.voz.narrar(texto),
                    lambda r: r.uso,
                    self.voz.timeout_s,
                )
                return res.mp3
            except FalloPaso:
                metrica.estado = "degradado"
                return None

        audios = list(await asyncio.gather(*(uno(t) for t in textos)))
        metrica.latencia_ms = int((time.perf_counter() - inicio) * 1000)  # tiempo de pared
        return audios
