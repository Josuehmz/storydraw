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
- Antes de pedir los fondos se lee el ambiente de cada escena (día, atardecer, noche, bajo el
  agua, interior) y se cambia el color del lugar que choque con el dibujo (ver `escena`). La
  paleta y la corrección de luz respetan ese ambiente, y lo que vuela o nada no lleva sombra.
- Sin imagen, se usa un fondo del banco y el cuento sale con aviso. Si la voz falla, el cuento
  se entrega escrito, con aviso (apagada no avisa). La voz solo lee texto que ya pasó la moderación.
- La voz tiene un tope de cuentos por día UTC (`ICupoVoz`, plan gratuito de Cloudflare). Pasado
  el tope, o si el proveedor responde que se acabó el cupo (429), el cuento sale sin voz y sin
  error: la app no muestra el botón de escuchar. Tras un 429 del cupo diario no se vuelve a
  llamar a la voz hasta el día UTC siguiente.
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
from datetime import UTC, date, datetime
from typing import Literal, TypeVar

from app.dominio.armonia import PaletaDibujo, guia_de_color
from app.dominio.composicion import Compositor, fondo_del_banco
from app.dominio.costos import Capacidad, Tarifario
from app.dominio.escena import (
    Ambiente,
    ambiente_de,
    en_el_aire,
    recolorear_escena,
    recolorear_texto,
)
from app.dominio.moderacion import Moderacion
from app.dominio.puertos import (
    AtributosDibujo,
    CuentoTexto,
    CupoAgotado,
    Hipotesis,
    IAlmacen,
    ICupoVoz,
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
# Informativo, no es un error: la app no muestra nada (el cuento sale sin botón de escuchar).
AVISO_VOZ_SIN_CUPO = "voz_sin_cupo"

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


@dataclass(frozen=True)
class PlanPagina:
    """Lo que se decide de cada página antes de pedir fondo y voz."""

    texto: str  # el que lee el niño (y narra la voz)
    escena: str  # la descripción visual que va al generador
    ambiente: Ambiente = "dia"
    aire: bool = False  # el protagonista vuela o nada: sin sombra ni suelo


def hoy_utc() -> date:
    return datetime.now(UTC).date()


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
        cupo_voz: ICupoVoz | None = None,
        reloj: Callable[[], date] = hoy_utc,
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
        # Tope de cuentos con voz por día UTC. None = sin tope.
        self.cupo_voz = cupo_voz
        self._reloj = reloj
        # Día UTC en que el proveedor dijo que se acabó su cupo diario: hasta mañana, sin voz.
        self._voz_agotada_el: date | None = None

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
                    # Sin cupo (429) no sirve reintentar: el cupo no vuelve en segundos.
                    if isinstance(exc, CupoAgotado):
                        break
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

        # El recorte (que corre desde el principio) se necesita ya: su paleta guía los fondos
        # y decide qué colores del lugar chocan con el dibujo.
        with medir(cuento_id, "espera_recorte"):
            recorte = await recorte_tarea
        paleta = await asyncio.to_thread(self.compositor.paleta, recorte)
        log.info(
            "cuento=%s paleta_dibujo=%s luminosidad=%.0f",
            cuento_id,
            paleta.familia,
            paleta.luminosidad,
        )
        plan = self.planear(cuento_id, personaje, paginas, paleta)

        async def escenarios_medidos() -> list[bytes]:
            with medir(cuento_id, "escenarios"):
                return await self._escenarios(
                    m_escenarios, [p.escena for p in plan], cuento_id, recorte, paleta, plan
                )

        async def narrar_medido() -> list[bytes | None]:
            with medir(cuento_id, "narrar"):
                return await self.narrar([p.texto for p in plan], m_narrar, resultado.avisos)

        fondos, audios = await asyncio.gather(escenarios_medidos(), narrar_medido())
        if m_escenarios.estado in ("degradado", "omitido"):
            resultado.avisos.append(AVISO_SIN_ESCENARIOS)
        # Con la voz apagada (`ninguno`) no hay aviso: es el estado normal. Solo si falló.
        if m_narrar.estado == "degradado":
            resultado.avisos.append(AVISO_SIN_NARRACION)

        # Composición y subida al almacén. Las páginas se componen a la vez, cada una en
        # su hilo: Pillow suelta el GIL en lo pesado y el bucle de eventos queda libre.
        def componer_medido(i: int) -> bytes:
            p = plan[i - 1]
            with medir(cuento_id, f"componer_{i}"):
                png, armonia = self.compositor.componer_armonico(
                    fondos[i - 1], recorte, i, p.ambiente, p.aire
                )
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
        for i, (pagina, png) in enumerate(zip(plan, pngs, strict=True), start=1):
            clave = clave_imagen(cuento_id, i)
            with medir(cuento_id, f"guardar_{i}"):
                await self.almacen.guardar(clave, png, "image/png")
                audio_clave = None
                if audios[i - 1] is not None:
                    audio_clave = clave_audio(cuento_id, i)
                    await self.almacen.guardar(audio_clave, audios[i - 1], "audio/mpeg")
            resultado.paginas.append(PaginaFinal(i, pagina.texto.strip(), clave, audio_clave))
        resultado.estado = "listo"

    def planear(
        self,
        cuento_id: str,
        personaje: str,
        paginas: list,
        paleta: PaletaDibujo,
    ) -> list[PlanPagina]:
        """Ambiente de cada escena, color del lugar que no choque con el dibujo y si vuela.

        El texto del niño solo cambia si nombra con ese mismo color un lugar («el trigal
        dorado»); la escena visual cambia siempre que choque. Al log van solo los colores.
        """
        plan = []
        for i, pagina in enumerate(paginas, start=1):
            ambiente = ambiente_de(pagina.escena, pagina.texto)
            escena, cambios_escena = recolorear_escena(pagina.escena, paleta.familia)
            texto, cambios_texto = recolorear_texto(pagina.texto, paleta.familia)
            aire = en_el_aire(personaje, ambiente)
            log.info(
                "cuento=%s pagina=%d ambiente=%s aire=%s color_escena=%s color_texto=%s",
                cuento_id,
                i,
                ambiente,
                aire,
                ",".join(f"{a}>{b}" for a, b in cambios_escena) or "-",
                ",".join(f"{a}>{b}" for a, b in cambios_texto) or "-",
            )
            plan.append(PlanPagina(texto, escena, ambiente, aire))
        return plan

    async def _hay_cupo_de_voz(self) -> bool:
        """Reserva el cupo de voz de este cuento. Sin tope configurado, siempre hay."""
        if self._voz_agotada_el is not None:
            if self._voz_agotada_el == self._reloj():
                return False
            self._voz_agotada_el = None  # nuevo día UTC: el proveedor ya repuso su cupo
        if self.cupo_voz is None:
            return True
        try:
            return await self.cupo_voz.reservar()
        except Exception as exc:  # sin base de datos no se sabe: se protege el cupo
            log.warning("cupo_voz no disponible error=%s", type(exc).__name__)
            return False

    async def narrar(
        self,
        textos: list[str],
        metrica: MetricaPaso | None = None,
        avisos: list[str] | None = None,
    ) -> list[bytes | None]:
        """Paso 5: un audio por página. Si una falla, esa página queda sin audio.

        Sin cupo de voz (el tope del día o un 429 del proveedor), el cuento entero sale sin
        voz: sin error y con el aviso informativo `voz_sin_cupo`, que la app no muestra.
        """
        metrica = metrica or MetricaPaso("narrar", self.voz.proveedor)
        sin_voz: list[bytes | None] = [None] * len(textos)
        if not self.voz.disponible:
            # Capacidad apagada: cuento escrito, sin llamar ni reintentar.
            metrica.estado = "omitido"
            return sin_voz

        def sin_cupo() -> list[bytes | None]:
            metrica.estado = "omitido"
            if avisos is not None and AVISO_VOZ_SIN_CUPO not in avisos:
                avisos.append(AVISO_VOZ_SIN_CUPO)
            return sin_voz

        if not await self._hay_cupo_de_voz():
            log.info("narrar sin_cupo: el cuento sale sin voz")
            return sin_cupo()
        inicio = time.perf_counter()
        cupo_del_proveedor = False

        async def uno(texto: str) -> bytes | None:
            nonlocal cupo_del_proveedor
            try:
                res = await self._con_reintentos(
                    metrica,
                    "voz",
                    lambda: self.voz.narrar(texto),
                    lambda r: r.uso,
                    self.voz.timeout_s,
                )
                return res.mp3
            except FalloPaso as fallo:
                if isinstance(fallo.causa, CupoAgotado):
                    cupo_del_proveedor = True
                    if fallo.causa.diario:
                        self._voz_agotada_el = self._reloj()
                metrica.estado = "degradado"
                return None

        audios = list(await asyncio.gather(*(uno(t) for t in textos)))
        metrica.latencia_ms = int((time.perf_counter() - inicio) * 1000)  # tiempo de pared
        if not any(audios) and self.cupo_voz is not None:
            # No salió ningún audio: este cuento no gastó el cupo del día.
            try:
                await self.cupo_voz.liberar()
            except Exception as exc:
                log.warning("cupo_voz no se pudo liberar error=%s", type(exc).__name__)
        if cupo_del_proveedor:
            # Un cuento narrado a medias confunde: o todas las páginas tienen voz o ninguna.
            log.warning("narrar proveedor_sin_cupo: el cuento sale sin voz")
            return sin_cupo()
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
        paleta: PaletaDibujo | None = None,
        plan: list[PlanPagina] | None = None,
    ) -> list[bytes]:
        if not self.imagen.disponible:
            # Capacidad apagada: fondo del banco sin llamar ni reintentar.
            metrica.estado = "omitido"
            return [fondo_del_banco(i) for i in range(len(escenas))]
        inicio = time.perf_counter()
        if paleta is None and recorte is not None:
            paleta = await asyncio.to_thread(self.compositor.paleta, recorte)
        planes = plan or [PlanPagina("", e, ambiente_de(e)) for e in escenas]

        def pedido(i: int, escena: str, reforzada: bool = False) -> str:
            # La escena (hábitat, en inglés) más la paleta que contrasta con el dibujo dentro
            # del ambiente de la escena.
            if paleta is None:
                return escena
            guia = guia_de_color(paleta, reforzada, planes[i].ambiente, planes[i].aire)
            return f"{escena.strip().rstrip('.')}. {guia}"

        async def otra_vez(i: int, escena: str, png: bytes) -> bytes:
            """Si el fondo se come al dibujo, un solo intento más; se queda el mejor."""
            assert recorte is not None  # noqa: S101 - solo se llama con recorte
            aire = planes[i].aire
            antes = await asyncio.to_thread(self.compositor.contraste, png, recorte, i + 1, aire)
            if antes >= self.compositor.contraste_minimo:
                log.info("cuento=%s fondo=%d contraste=%.1f", cuento_id, i + 1, antes)
                return png
            despues = None
            try:
                with medir(cuento_id, f"fondo_{i + 1}_otra_vez"):
                    metrica.intentos += 1
                    res = await asyncio.wait_for(
                        self.imagen.generar_fondo(pedido(i, escena, reforzada=True)),
                        timeout=self.imagen.timeout_s or self.timeout_s,
                    )
                metrica.costo_usd += self.tarifario.costo("imagen", res.uso)
                despues = await asyncio.to_thread(
                    self.compositor.contraste, res.png, recorte, i + 1, aire
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
                        lambda: self.imagen.generar_fondo(pedido(i, escena)),
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
