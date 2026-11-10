"""Composición de páginas, sin IA externa.

El dibujo del niño no se reinterpreta: se recorta y se integra en el fondo de cada página
(contraste, sombra de contacto, luz y textura: ver `armonia`). Todo ocurre en memoria; el
dibujo original nunca se escribe en disco ni en el almacén, solo las páginas ya compuestas.
"""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from app.dominio.armonia import (
    CONTRASTE_MINIMO,
    Colocacion,
    PaletaDibujo,
    ajustar_a_la_luz,
    analizar,
    armonizar_fondo,
    contraste,
    luz_alrededor,
    luz_de_escena,
    sombra_de_contacto,
    suavizar_borde,
    textura_de_lapiz,
)
from app.dominio.escena import Ambiente
from app.dominio.puertos import IRecortador

log = logging.getLogger(__name__)

LADO_PAGINA = 1024
_MAX_PIXELES_ENTRADA = 4096 * 4096


class DibujoInvalido(ValueError):
    pass


def abrir_dibujo(datos: bytes) -> bytes:
    """Valida el archivo y devuelve un PNG RGB con fondo blanco forzado.

    Sobre fondo transparente los modelos ven trazos fantasma: el blanco es un requisito.
    """
    try:
        with Image.open(io.BytesIO(datos)) as img:
            if img.format not in {"PNG", "JPEG", "WEBP"}:
                raise DibujoInvalido("formato no admitido")
            if img.width * img.height > _MAX_PIXELES_ENTRADA:
                raise DibujoInvalido("imagen demasiado grande")
            img.load()
            rgba = img.convert("RGBA")
    except DibujoInvalido:
        raise
    except Exception as exc:  # Pillow lanza varios tipos según el archivo
        raise DibujoInvalido("no es una imagen válida") from exc
    fondo = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    fondo.alpha_composite(rgba)
    salida = io.BytesIO()
    fondo.convert("RGB").save(salida, format="PNG")
    return salida.getvalue()


class RecortadorUmbral(IRecortador):
    """Vuelve transparente lo casi blanco y recorta al contenido. Solo Pillow."""

    def __init__(self, umbral: int = 235):
        self.umbral = umbral

    def recortar(self, png_blanco: bytes) -> bytes:
        with Image.open(io.BytesIO(png_blanco)) as img:
            rgb = img.convert("RGB")
        gris = ImageOps.grayscale(rgb)
        mascara = gris.point(lambda v: 255 if v < self.umbral else 0)
        mascara = mascara.filter(ImageFilter.MaxFilter(3))
        recorte = rgb.convert("RGBA")
        recorte.putalpha(mascara)
        caja = mascara.getbbox()
        if caja:
            recorte = recorte.crop(caja)
        salida = io.BytesIO()
        recorte.save(salida, format="PNG")
        return salida.getvalue()


class RecortadorRembg(IRecortador):
    """Recorte con rembg (modelo local, sin llamadas externas). Degrada al umbral."""

    def __init__(self) -> None:
        self._sesion = None
        self._respaldo = RecortadorUmbral()

    def recortar(self, png_blanco: bytes) -> bytes:
        try:
            from rembg import new_session, remove

            if self._sesion is None:
                self._sesion = new_session("u2net")
            datos = remove(png_blanco, session=self._sesion)
            with Image.open(io.BytesIO(datos)) as img:
                rgba = img.convert("RGBA")
            caja = rgba.getchannel("A").getbbox()
            if not caja:
                return self._respaldo.recortar(png_blanco)
            salida = io.BytesIO()
            rgba.crop(caja).save(salida, format="PNG")
            return salida.getvalue()
        except Exception:
            log.warning("rembg no disponible o falló; se usa el recorte por umbral")
            return self._respaldo.recortar(png_blanco)


@dataclass(frozen=True)
class Armonia:
    """Lo medido al componer una página (va al log; no describe al niño)."""

    contraste_inicial: float
    contraste_final: float

    @property
    def corregido(self) -> bool:
        return self.contraste_final != self.contraste_inicial


def _abrir_rgba(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as img:
        return img.convert("RGBA")


def _colocar(
    dibujo: Image.Image, numero: int, aire: bool = False
) -> tuple[Image.Image, Colocacion]:
    """Escala el dibujo y lo apoya en el suelo despejado de la parte baja de la página.

    El protagonista ocupa ~55 % de la página y varía un poco de posición entre páginas. Lo que
    vuela o nada (`aire`) no se apoya: queda en el centro, un poco más arriba.
    """
    maximo = int(LADO_PAGINA * 0.55)
    escala = min(maximo / max(dibujo.width, 1), maximo / max(dibujo.height, 1))
    nuevo = (max(1, int(dibujo.width * escala)), max(1, int(dibujo.height * escala)))
    dibujo = dibujo.resize(nuevo, Image.LANCZOS)
    desplazamientos = (-0.18, 0.0, 0.18)
    dx = int(LADO_PAGINA * desplazamientos[(numero - 1) % 3])
    x = (LADO_PAGINA - dibujo.width) // 2 + dx
    if aire:
        y = max(0, (LADO_PAGINA - dibujo.height) // 2 - int(LADO_PAGINA * 0.05))
    else:
        y = LADO_PAGINA - dibujo.height - int(LADO_PAGINA * 0.07)
    return dibujo, Colocacion(x, y, dibujo.width, dibujo.height)


def _componer_recortado(base: Image.Image, capa: Image.Image, destino: tuple[int, int]) -> None:
    """`alpha_composite` que admite que la capa se salga de la página por cualquier lado."""
    x, y = destino
    caja = (
        max(0, -x),
        max(0, -y),
        min(capa.width, base.width - x),
        min(capa.height, base.height - y),
    )
    if caja[0] >= caja[2] or caja[1] >= caja[3]:
        return
    base.alpha_composite(capa.crop(caja), (x + caja[0], y + caja[1]))


class Compositor:
    def __init__(self, recortador: IRecortador, contraste_minimo: float = CONTRASTE_MINIMO):
        self._recortador = recortador
        self.contraste_minimo = contraste_minimo

    def recortar(self, png_blanco: bytes) -> bytes:
        return self._recortador.recortar(png_blanco)

    def paleta(self, recorte_png: bytes) -> PaletaDibujo:
        """Brillo y tono del dibujo, para pedir un fondo que contraste."""
        return analizar(_abrir_rgba(recorte_png))

    def contraste(
        self, fondo_png: bytes, recorte_png: bytes, numero: int, aire: bool = False
    ) -> float:
        """Contraste (mediana de ΔE00) entre el dibujo y el fondo donde se colocará."""
        fondo = _abrir_rgba(fondo_png).resize((LADO_PAGINA, LADO_PAGINA))
        dibujo, donde = _colocar(_abrir_rgba(recorte_png), numero, aire)
        return contraste(fondo, dibujo, donde)

    def componer(
        self,
        fondo_png: bytes,
        recorte_png: bytes,
        numero: int,
        ambiente: Ambiente = "dia",
        aire: bool = False,
    ) -> bytes:
        return self.componer_armonico(fondo_png, recorte_png, numero, ambiente, aire)[0]

    def componer_armonico(
        self,
        fondo_png: bytes,
        recorte_png: bytes,
        numero: int,
        ambiente: Ambiente = "dia",
        aire: bool = False,
    ) -> tuple[bytes, Armonia]:
        """Monta el dibujo sobre el fondo para que parezca de la misma escena.

        1. Un dibujo oscuro de noche, bajo techo o bajo el agua, o lo que vuela o nada si es
           oscuro, lleva detrás un halo de luz suave del ambiente (farol, luna, sol).
        2. Si aun así el dibujo se confunde con la zona del fondo, se corrige la luz de esa zona
           sin cambiar el ambiente (`ambiente`: de noche, solo alrededor del dibujo).
        3. Sombra de contacto bajo la base del dibujo (apoyado, no flotando), salvo si vuela o
           nada (`aire`): entonces no hay suelo bajo él.
        4. Ajuste leve del dibujo a la luz de la escena y borde sin halo blanco.
        5. La misma textura de lápiz y papel por encima de todo.
        """
        fondo = _abrir_rgba(fondo_png).resize((LADO_PAGINA, LADO_PAGINA))
        original = _abrir_rgba(recorte_png)
        paleta = analizar(original)
        dibujo, donde = _colocar(original, numero, aire)
        if paleta.oscuro and (aire or ambiente in ("noche", "interior", "bajo_agua")):
            fondo = luz_alrededor(fondo, donde, ambiente, 0.45 if ambiente != "dia" else 0.3)
        armonizado, inicial, final = armonizar_fondo(
            fondo, dibujo, donde, paleta, self.contraste_minimo, ambiente
        )
        pagina = armonizado.convert("RGBA")
        luz = luz_de_escena(pagina)
        if not aire:
            sombra, donde_sombra = sombra_de_contacto(dibujo, donde, luz)
            _componer_recortado(pagina, sombra, donde_sombra)
        pagina.alpha_composite(suavizar_borde(ajustar_a_la_luz(dibujo, luz)), (donde.x, donde.y))
        pagina = textura_de_lapiz(pagina)
        salida = io.BytesIO()
        # Sin optimize: con la textura tardaba ~4 s por página para ahorrar ~5 % de peso.
        pagina.save(salida, format="PNG")
        return salida.getvalue(), Armonia(inicial, final)


_PALETAS = (
    ((135, 206, 250), (255, 248, 220), (120, 190, 90)),  # pradera
    ((255, 183, 120), (255, 236, 200), (90, 160, 120)),  # atardecer
    ((30, 40, 100), (90, 70, 160), (60, 90, 140)),  # noche
    ((120, 210, 230), (220, 250, 255), (60, 140, 200)),  # mar
)


def fondo_del_banco(indice: int) -> bytes:
    """Fondo de respaldo cuando falla la generación de imagen. Se dibuja, no se descarga."""
    cielo, horizonte, suelo = _PALETAS[indice % len(_PALETAS)]
    img = Image.new("RGB", (LADO_PAGINA, LADO_PAGINA))
    dib = ImageDraw.Draw(img)
    for y in range(LADO_PAGINA):
        t = y / LADO_PAGINA
        color = tuple(int(cielo[i] + (horizonte[i] - cielo[i]) * t) for i in range(3))
        dib.line([(0, y), (LADO_PAGINA, y)], fill=color)
    base = int(LADO_PAGINA * 0.72)
    puntos = [(0, LADO_PAGINA)]
    for x in range(0, LADO_PAGINA + 1, 16):
        puntos.append((x, base + int(40 * math.sin(x / 140 + indice))))
    puntos.append((LADO_PAGINA, LADO_PAGINA))
    dib.polygon(puntos, fill=suelo)
    sol = (int(LADO_PAGINA * 0.8), int(LADO_PAGINA * 0.18))
    dib.ellipse([sol[0] - 70, sol[1] - 70, sol[0] + 70, sol[1] + 70], fill=(255, 230, 110))
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()
