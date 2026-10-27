"""Orquestador del pipeline: asyncio, cuatro pasos, reintento por paso y degradación.

Pasos: 1 identificar (visión, opcional) · 2 escribir (texto) · 3 moderar (obligatorio) ·
4 escenarios (imagen). Después, la composición monta las páginas y las sube al almacén.
El cuento sale sin narración: se lee en pantalla.

- Cada paso se reintenta por separado; un fallo no rehace el cuento entero.
- La visión da el personaje (si el niño no lo dijo) y los rasgos del dibujo (colores,
  elementos, emoción), que viajan al paso del cuento para que no invente otros.
- Sin visión, se usa lo que el niño escribió (o un personaje genérico) y no hay rasgos.
- Un cuento con menos de 3 páginas no se entrega: cuenta como intento fallido del paso.
- Sin imagen, se usa un fondo del banco y el cuento sale con aviso.
- Una capacidad apagada (`PROVEEDOR_*=ninguno`) no se llama ni se reintenta.
- Sin cuento o sin moderación aprobada, no hay nada que mostrar: el niño no ve nada.
- Tiempos: cada llamada tiene un tope (cuerpo de la respuesta incluido); si se agota, se
  reintenta una sola vez. El cuento entero tiene otro tope y, si se pasa, falla limpio.
  Cada etapa deja su duración en el log (`cuento=<id> etapa=<nombre> ms=<n>`), sin datos
  del niño.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal, TypeVar

from app.dominio.composicion import Compositor, fondo_del_banco
from app.dominio.costos import Capacidad, Tarifario
from app.dominio.moderacion import Moderacion
from app.dominio.puertos import (
    AtributosDibujo,
    CuentoTexto,
    Hipotesis,
    IAlmacen,
    IImagen,
    ITexto,
    IVision,
    SolicitudCuento,
    Uso,
)

log = logging.getLogger(__name__)
T = TypeVar("T")

PERSONAJE_GENERICO = "un amigo mágico"
AVISO_SIN_ESCENARIOS = "sin_escenarios"
AVISO_SIN_IDENTIFICACION = "sin_identificacion"
AVISO_TIEMPO_AGOTADO = "tiempo_agotado"

PAGINAS = 3

Estado = Literal["listo", "rechazado", "fallido"]


class CuentoIncompleto(ValueError):
    """El modelo devolvió menos páginas de las pedidas: se reintenta, no se entrega."""


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


@dataclass
class ResultadoIdentificacion:
    disponible: bool
    hipotesis: list[Hipotesis]
    metrica: MetricaPaso
    atributos: AtributosDibujo = field(default_factory=AtributosDibujo)


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


@contextmanager
def medir(cuento_id: str, etapa: str) -> Iterator[None]:
    """Registra en INFO cuánto tardó una etapa. Solo id y milisegundos: nada del niño."""
    inicio = time.perf_counter()
    try:
        yield
    finally:
        ms = int((time.perf_counter() - inicio) * 1000)
        log.info("cuento=%s etapa=%s ms=%d", cuento_id, etapa, ms)


class Orquestador:
    def __init__(
        self,
        *,
        vision: IVision,
        texto: ITexto,
        imagen: IImagen,
        moderacion: Moderacion,
        compositor: Compositor,
        almacen: IAlmacen,
        tarifario: Tarifario,
        reintentos: int = 2,
        espera_base_s: float = 0.5,
        max_regeneraciones: int = 2,
        timeout_s: float = 60.0,
        tiempo_maximo_s: float | None = None,
    ):
        self.vision = vision
        self.texto = texto
        self.imagen = imagen
        self.moderacion = moderacion
        self.compositor = compositor
        self.almacen = almacen
        self.tarifario = tarifario
        self.reintentos = reintentos
        self.espera_base_s = espera_base_s
        self.max_regeneraciones = max_regeneraciones
        self.timeout_s = timeout_s
        # Tope del cuento entero (None = sin tope, p. ej. Ollama por CPU)
        self.tiempo_maximo_s = tiempo_maximo_s

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
        tiempos_agotados = 0
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
                    # Un tiempo agotado ya costó el tope entero: se reintenta una sola vez
                    # y, si vuelve a agotarse, el paso falla limpio (o se degrada).
                    if isinstance(exc, TimeoutError):
                        tiempos_agotados += 1
                        if tiempos_agotados >= 2:
                            break
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
        return ResultadoIdentificacion(
            bool(hipotesis), hipotesis, metrica, self._filtrar_atributos(res.atributos)
        )

    def _filtrar_atributos(self, atributos: AtributosDibujo) -> AtributosDibujo:
        """Los rasgos van al prompt del cuento: pasan el filtro local como las hipótesis."""

        def ok(texto: str) -> bool:
            return bool(texto) and self.moderacion.revisar_local(texto).aprobado

        return AtributosDibujo(
            colores=tuple(c for c in atributos.colores if ok(c)),
            elementos=tuple(e for e in atributos.elementos if ok(e)),
            emocion=atributos.emocion if ok(atributos.emocion) else "",
        )

    # ---------------------------------------------------------------- pipeline

    async def crear_cuento(
        self, cuento_id: str, dibujo_png: bytes, personaje: str | None, edad: int
    ) -> ResultadoCuento:
        inicio = time.perf_counter()
        resultado = ResultadoCuento(estado="fallido")
        try:
            await asyncio.wait_for(
                self._pipeline(resultado, cuento_id, dibujo_png, personaje, edad),
                timeout=self.tiempo_maximo_s,
            )
        except TimeoutError:
            # Tope del cuento entero: falla limpio, sin páginas a medias.
            log.warning("cuento=%s tiempo_agotado tope_s=%s", cuento_id, self.tiempo_maximo_s)
            resultado.estado = "fallido"
            resultado.paginas.clear()
            resultado.avisos.append(AVISO_TIEMPO_AGOTADO)
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
        def recortar_medido() -> bytes:
            with medir(cuento_id, "recorte"):
                return self.compositor.recortar(dibujo_png)

        recorte_tarea = asyncio.create_task(asyncio.to_thread(recortar_medido))

        # Paso 1 · identificar. Aunque el niño ya dijo qué dibujó, la visión lee los rasgos
        # del dibujo (colores, elementos, emoción) para que el cuento no invente otros.
        personaje = (personaje or "").strip()[:120]
        with medir(cuento_id, "identificar"):
            ident = await self.identificar(dibujo_png)
        resultado.pasos.append(ident.metrica)
        atributos = ident.atributos
        if not personaje:
            if ident.disponible:
                personaje = ident.hipotesis[0].etiqueta
            else:
                personaje = PERSONAJE_GENERICO
                resultado.avisos.append(AVISO_SIN_IDENTIFICACION)
        resultado.personaje = personaje
        solicitud = SolicitudCuento(personaje, edad, PAGINAS, atributos)

        # Pasos 2 y 3 · escribir y moderar, con regeneración si se rechaza
        m_escribir = MetricaPaso("escribir", self.texto.proveedor)
        m_moderar = MetricaPaso("moderar", self.moderacion.proveedor)
        resultado.pasos += [m_escribir, m_moderar]

        entrada = personaje
        if not atributos.vacio:
            entrada += f"\n({atributos.como_texto()})"
        with medir(cuento_id, "moderar_entrada"):
            entrada_ok = await self._moderar(m_moderar, resultado, "entrada", entrada)
        if not entrada_ok:
            m_escribir.estado = "omitido"
            resultado.estado = "rechazado"
            recorte_tarea.cancel()
            return

        cuento: CuentoTexto | None = None
        for _ in range(self.max_regeneraciones + 1):
            try:
                with medir(cuento_id, "escribir"):
                    candidato = await self._con_reintentos(
                        m_escribir,
                        "texto",
                        lambda: self._escribir_completo(solicitud),
                        lambda r: r.uso,
                        self.texto.timeout_s,
                    )
            except FalloPaso:
                m_escribir.estado = "fallido"
                resultado.estado = "fallido"
                recorte_tarea.cancel()
                return
            paginas_candidato = candidato.paginas[:PAGINAS]
            completo = candidato.titulo + "\n" + "\n".join(p.texto for p in paginas_candidato)
            with medir(cuento_id, "moderar_cuento"):
                aprobado = await self._moderar(m_moderar, resultado, "cuento", completo)
            if aprobado:
                cuento = candidato
                break
        if cuento is None:
            resultado.estado = "rechazado"
            recorte_tarea.cancel()
            return

        paginas = cuento.paginas[:PAGINAS]
        resultado.titulo = cuento.titulo.strip()[:200]

        # Paso 4 · escenarios
        m_escenarios = MetricaPaso("escenarios", self.imagen.proveedor)
        resultado.pasos.append(m_escenarios)
        with medir(cuento_id, "escenarios"):
            fondos = await self._escenarios(m_escenarios, [p.escena for p in paginas], cuento_id)
        if m_escenarios.estado in ("degradado", "omitido"):
            resultado.avisos.append(AVISO_SIN_ESCENARIOS)

        # Composición y subida al almacén. Las páginas se componen a la vez, cada una en
        # su hilo: Pillow suelta el GIL en lo pesado y el bucle de eventos queda libre.
        with medir(cuento_id, "espera_recorte"):
            recorte = await recorte_tarea

        def componer_medido(i: int) -> bytes:
            with medir(cuento_id, f"componer_{i}"):
                return self.compositor.componer(fondos[i - 1], recorte, i)

        with medir(cuento_id, "componer"):
            pngs = await asyncio.gather(
                *(asyncio.to_thread(componer_medido, i) for i in range(1, len(paginas) + 1))
            )
        for i, (pagina, png) in enumerate(zip(paginas, pngs, strict=True), start=1):
            clave = clave_imagen(cuento_id, i)
            with medir(cuento_id, f"guardar_{i}"):
                await self.almacen.guardar(clave, png, "image/png")
            resultado.paginas.append(PaginaFinal(i, pagina.texto.strip(), clave))
        resultado.estado = "listo"

    async def _escribir_completo(self, solicitud: SolicitudCuento) -> CuentoTexto:
        """Un cuento con menos páginas de las pedidas cuenta como intento fallido."""
        cuento = await self.texto.escribir_cuento(solicitud)
        validas = [p for p in cuento.paginas if p.texto.strip()]
        if len(validas) < solicitud.paginas:
            raise CuentoIncompleto(f"{len(validas)} de {solicitud.paginas} páginas")
        return CuentoTexto(cuento.titulo, validas, cuento.uso)

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

    async def _escenarios(
        self, metrica: MetricaPaso, escenas: list[str], cuento_id: str = "-"
    ) -> list[bytes]:
        if not self.imagen.disponible:
            # Capacidad apagada: fondo del banco sin llamar ni reintentar.
            metrica.estado = "omitido"
            return [fondo_del_banco(i) for i in range(len(escenas))]
        inicio = time.perf_counter()

        async def uno(i: int, escena: str) -> bytes:
            try:
                with medir(cuento_id, f"fondo_{i + 1}"):
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
