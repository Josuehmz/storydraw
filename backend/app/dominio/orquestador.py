"""Orquestador del pipeline: asyncio, cinco pasos, reintento por paso y degradación.

Pasos: 1 identificar (visión, opcional) · 2 escribir (texto) · 3 moderar (obligatorio) ·
4 escenarios (imagen) · 5 narrar (voz). Los pasos 4 y 5 corren en paralelo. Después, la
composición monta las páginas y las sube al almacén.

- Cada paso se reintenta por separado; un fallo no rehace el cuento entero.
- La visión da el personaje (si el niño no lo dijo) y los rasgos del dibujo (colores,
  elementos, emoción), que viajan al paso del cuento para que no invente otros.
- Sin visión, se usa lo que el niño escribió (o un personaje genérico) y no hay rasgos.
- Un cuento con menos de 3 páginas no se entrega: cuenta como intento fallido del paso.
- Los fondos se piden con una paleta que contraste con el dibujo (se lee del recorte antes
  de pedirlos). Si un fondo queda sin contraste con el dibujo, la composición corrige su luz
  (ver `armonia`); opcionalmente, antes se pide otro una sola vez y se queda el mejor.
- Sin imagen, se usa un fondo del banco y el cuento sale con aviso. Si la voz falla, el cuento
  se entrega escrito, con aviso (apagada no avisa). La voz solo lee texto que ya pasó la moderación.
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

from app.dominio.armonia import guia_de_color
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
    audio_clave: str | None = None


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


def clave_audio(cuento_id: str, numero: int) -> str:
    return f"cuentos/{cuento_id}/audio/{numero}.mp3"


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
        voz: IVoz,
        moderacion: Moderacion,
        compositor: Compositor,
        almacen: IAlmacen,
        tarifario: Tarifario,
        reintentos: int = 2,
        espera_base_s: float = 0.5,
        max_regeneraciones: int = 2,
        timeout_s: float = 60.0,
        tiempo_maximo_s: float | None = None,
        regenerar_fondo_sin_contraste: bool = False,
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
        # Tope del cuento entero (None = sin tope, p. ej. Ollama por CPU)
        self.tiempo_maximo_s = tiempo_maximo_s
        # Un fondo que no contrasta con el dibujo se pide otra vez (una sola, por página).
        # Apagado por defecto: ver REGENERAR_FONDO_SIN_CONTRASTE en la configuración.
        self.regenerar_fondo_sin_contraste = regenerar_fondo_sin_contraste

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
        self,
        cuento_id: str,
        dibujo_png: bytes,
        personaje: str | None,
        edad: int,
        nombre: str | None = None,
    ) -> ResultadoCuento:
        inicio = time.perf_counter()
        resultado = ResultadoCuento(estado="fallido")
        try:
            await asyncio.wait_for(
                self._pipeline(resultado, cuento_id, dibujo_png, personaje, edad, nombre),
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
        nombre: str | None = None,
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
        nombre = (nombre or "").strip()[:40]
        solicitud = SolicitudCuento(personaje, edad, PAGINAS, atributos, nombre)

        # Pasos 2 y 3 · escribir y moderar, con regeneración si se rechaza
        m_escribir = MetricaPaso("escribir", self.texto.proveedor)
        m_moderar = MetricaPaso("moderar", self.moderacion.proveedor)
        resultado.pasos += [m_escribir, m_moderar]

        entrada = f"{personaje} llamado {nombre}" if nombre else personaje
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

        # Pasos 4 y 5 · escenarios y narración en paralelo; ninguno bloquea al otro.
        # La voz lee el texto ya moderado: nunca se narra (ni se paga) algo no aprobado.
        m_escenarios = MetricaPaso("escenarios", self.imagen.proveedor)
        m_narrar = MetricaPaso("narrar", self.voz.proveedor)
        resultado.pasos += [m_escenarios, m_narrar]

        # El recorte (que corre desde el principio) se necesita ya: su paleta guía los fondos.
        with medir(cuento_id, "espera_recorte"):
            recorte = await recorte_tarea

        async def escenarios_medidos() -> list[bytes]:
            with medir(cuento_id, "escenarios"):
                return await self._escenarios(
                    m_escenarios, [p.escena for p in paginas], cuento_id, recorte
                )

        async def narrar_medido() -> list[bytes | None]:
            with medir(cuento_id, "narrar"):
                return await self.narrar([p.texto for p in paginas], m_narrar)

        fondos, audios = await asyncio.gather(escenarios_medidos(), narrar_medido())
        if m_escenarios.estado in ("degradado", "omitido"):
            resultado.avisos.append(AVISO_SIN_ESCENARIOS)
        # Con la voz apagada (`ninguno`) no hay aviso: es el estado normal. Solo si falló.
        if m_narrar.estado == "degradado":
            resultado.avisos.append(AVISO_SIN_NARRACION)

        # Composición y subida al almacén. Las páginas se componen a la vez, cada una en
        # su hilo: Pillow suelta el GIL en lo pesado y el bucle de eventos queda libre.
        def componer_medido(i: int) -> bytes:
            with medir(cuento_id, f"componer_{i}"):
                png, armonia = self.compositor.componer_armonico(fondos[i - 1], recorte, i)
            log.info(
                "cuento=%s pagina=%d contraste=%.1f contraste_final=%.1f",
                cuento_id,
                i,
                armonia.contraste_inicial,
                armonia.contraste_final,
            )
            return png

        with medir(cuento_id, "componer"):
            pngs = await asyncio.gather(
                *(asyncio.to_thread(componer_medido, i) for i in range(1, len(paginas) + 1))
            )
        for i, (pagina, png) in enumerate(zip(paginas, pngs, strict=True), start=1):
            clave = clave_imagen(cuento_id, i)
            with medir(cuento_id, f"guardar_{i}"):
                await self.almacen.guardar(clave, png, "image/png")
                audio_clave = None
                if audios[i - 1] is not None:
                    audio_clave = clave_audio(cuento_id, i)
                    await self.almacen.guardar(audio_clave, audios[i - 1], "audio/mpeg")
            resultado.paginas.append(PaginaFinal(i, pagina.texto.strip(), clave, audio_clave))
        resultado.estado = "listo"

    async def narrar(
        self, textos: list[str], metrica: MetricaPaso | None = None
    ) -> list[bytes | None]:
        """Paso 5: un audio por página. Si una falla, esa página queda sin audio."""
        metrica = metrica or MetricaPaso("narrar", self.voz.proveedor)
        if not self.voz.disponible:
            # Capacidad apagada: cuento escrito, sin llamar ni reintentar.
            metrica.estado = "omitido"
            return [None] * len(textos)
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
        self,
        metrica: MetricaPaso,
        escenas: list[str],
        cuento_id: str = "-",
        recorte: bytes | None = None,
    ) -> list[bytes]:
        if not self.imagen.disponible:
            # Capacidad apagada: fondo del banco sin llamar ni reintentar.
            metrica.estado = "omitido"
            return [fondo_del_banco(i) for i in range(len(escenas))]
        inicio = time.perf_counter()
        paleta = None
        if recorte is not None:
            paleta = await asyncio.to_thread(self.compositor.paleta, recorte)
            log.info(
                "cuento=%s paleta_dibujo=%s luminosidad=%.0f",
                cuento_id,
                paleta.familia,
                paleta.luminosidad,
            )

        def pedido(escena: str, reforzada: bool = False) -> str:
            # La escena (hábitat, en inglés) más la paleta que contrasta con el dibujo.
            if paleta is None:
                return escena
            return f"{escena.strip().rstrip('.')}. {guia_de_color(paleta, reforzada)}"

        async def otra_vez(i: int, escena: str, png: bytes) -> bytes:
            """Si el fondo se come al dibujo, un solo intento más; se queda el mejor."""
            assert recorte is not None  # noqa: S101 - solo se llama con recorte
            antes = await asyncio.to_thread(self.compositor.contraste, png, recorte, i + 1)
            if antes >= self.compositor.contraste_minimo:
                log.info("cuento=%s fondo=%d contraste=%.1f", cuento_id, i + 1, antes)
                return png
            despues = None
            try:
                with medir(cuento_id, f"fondo_{i + 1}_otra_vez"):
                    metrica.intentos += 1
                    res = await asyncio.wait_for(
                        self.imagen.generar_fondo(pedido(escena, reforzada=True)),
                        timeout=self.imagen.timeout_s or self.timeout_s,
                    )
                metrica.costo_usd += self.tarifario.costo("imagen", res.uso)
                despues = await asyncio.to_thread(
                    self.compositor.contraste, res.png, recorte, i + 1
                )
                if despues > antes:
                    png = res.png
            except Exception as exc:  # se queda el primero; la composición corrige la zona
                log.warning(
                    "cuento=%s fondo=%d otra_vez error=%s", cuento_id, i + 1, type(exc).__name__
                )
            log.info(
                "cuento=%s fondo=%d contraste=%.1f otra_vez=%s",
                cuento_id,
                i + 1,
                antes,
                "-" if despues is None else f"{despues:.1f}",
            )
            return png

        async def uno(i: int, escena: str) -> bytes:
            try:
                with medir(cuento_id, f"fondo_{i + 1}"):
                    res = await self._con_reintentos(
                        metrica,
                        "imagen",
                        lambda: self.imagen.generar_fondo(pedido(escena)),
                        lambda r: r.uso,
                        self.imagen.timeout_s,
                    )
            except FalloPaso:
                metrica.estado = "degradado"
                return fondo_del_banco(i)
            if recorte is None or not self.regenerar_fondo_sin_contraste:
                return res.png
            return await otra_vez(i, escena, res.png)

        fondos = list(await asyncio.gather(*(uno(i, e) for i, e in enumerate(escenas))))
        metrica.latencia_ms = int((time.perf_counter() - inicio) * 1000)  # tiempo de pared
        return fondos
