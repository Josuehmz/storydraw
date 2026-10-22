"""Composición de páginas, sin IA externa.

El dibujo del niño no se reinterpreta: se recorta y se monta encima del fondo de cada
página. Todo ocurre en memoria; el dibujo original nunca se escribe en disco ni en el
almacén, solo las páginas ya compuestas.
"""

from __future__ import annotations

import io
import logging
import math

from PIL import Image, ImageDraw, ImageFilter, ImageOps

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


class Compositor:
    def __init__(self, recortador: IRecortador):
        self._recortador = recortador

    def recortar(self, png_blanco: bytes) -> bytes:
        return self._recortador.recortar(png_blanco)

    def componer(self, fondo_png: bytes, recorte_png: bytes, numero: int) -> bytes:
        with Image.open(io.BytesIO(fondo_png)) as f:
            fondo = f.convert("RGBA").resize((LADO_PAGINA, LADO_PAGINA))
        with Image.open(io.BytesIO(recorte_png)) as r:
            dibujo = r.convert("RGBA")
        # El protagonista ocupa ~55 % de la página; varía un poco de posición por página.
        maximo = int(LADO_PAGINA * 0.55)
        escala = min(maximo / max(dibujo.width, 1), maximo / max(dibujo.height, 1))
        nuevo = (max(1, int(dibujo.width * escala)), max(1, int(dibujo.height * escala)))
        dibujo = dibujo.resize(nuevo, Image.LANCZOS)
        desplazamientos = (-0.18, 0.0, 0.18)
        dx = int(LADO_PAGINA * desplazamientos[(numero - 1) % 3])
        x = (LADO_PAGINA - dibujo.width) // 2 + dx
        y = LADO_PAGINA - dibujo.height - int(LADO_PAGINA * 0.08)
        sombra = Image.new("RGBA", fondo.size, (0, 0, 0, 0))
        alfa = dibujo.getchannel("A").point(lambda v: 90 if v > 0 else 0)
        sombra.paste((0, 0, 0, 255), (x + 10, y + 12), alfa)
        fondo.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(8)))
        fondo.alpha_composite(dibujo, (x, y))
        salida = io.BytesIO()
        fondo.convert("RGB").save(salida, format="PNG", optimize=True)
        return salida.getvalue()


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
