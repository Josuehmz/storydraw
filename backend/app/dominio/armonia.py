"""Armonía de color entre el dibujo del niño y el fondo de cada página. Solo Pillow.

Antes el fondo se pedía sin mirar el dibujo: un pollito amarillo caía en un trigal amarillo y
desaparecía. Ahora, en tres tiempos:

1. **Antes del fondo:** se leen el brillo y el tono dominante del dibujo (sin lo transparente)
   y se pide el fondo con una paleta que contraste (`guia_de_color`).
2. **Después del fondo:** se mide el contraste entre el dibujo y la zona del fondo donde va
   (`contraste`: mediana de ΔE00 —CIEDE2000— en Lab, píxel a píxel). Si queda bajo el umbral, el
   orquestador puede pedir otro fondo una vez y, si aun así no alcanza, se corrige el tono y el
   brillo de esa zona (`armonizar_fondo`).
3. **Al componer** (en `composicion`): sombra de contacto, ajuste leve del dibujo a la luz de la
   escena y una textura de lápiz y papel por encima de todo.

Nada de esto describe al niño: son colores del dibujo, y no salen del servidor salvo como
nombres de color en inglés dentro del prompt del fondo.
"""

from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from statistics import median

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

# Por debajo de esta mediana de ΔE00 el dibujo se confunde con el fondo. Medido el 2026-11-09
# con seis dibujos de prueba sobre fondos reales de flux: los que se veían mal (pollito
# amarillo en un trigal, nube clara entre nubes) daban 15-17; a medias, 22-25; los que se
# leían bien, 31 o más. ΔE76 no servía: premia la croma y daba 52 al pollito que «ni se ve».
CONTRASTE_MINIMO = 30.0

# Lado máximo al que se reduce el dibujo para medir: rápido y suficiente para el color.
_LADO_MEDIDA = 64
# Croma (C* de Lab) por debajo del cual un color cuenta como gris, negro o blanco.
_CROMA_GRIS = 12.0


# ---------------------------------------------------------------------------- color


@lru_cache(maxsize=40_000)
def _lab_cuantizado(r: int, g: int, b: int) -> tuple[float, float, float]:
    def lineal(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    rl, gl, bl = lineal(r), lineal(g), lineal(b)
    x = (0.4124 * rl + 0.3576 * gl + 0.1805 * bl) / 0.95047
    y = 0.2126 * rl + 0.7152 * gl + 0.0722 * bl
    z = (0.0193 * rl + 0.1192 * gl + 0.9505 * bl) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """sRGB (0-255) a CIE Lab (D65). Se cuantiza a 6 bits por canal para cachear."""
    r, g, b = rgb[:3]
    return _lab_cuantizado(r & 0xFC, g & 0xFC, b & 0xFC)


def delta_e(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 (ΔE00): la diferencia de color que percibe el ojo. ~2 apenas se nota."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c_media = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_media**7 / (c_media**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    d_l, d_c = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        d_h = 0.0
        h_media = h1p + h2p
    else:
        d_h = h2p - h1p
        if d_h > 180:
            d_h -= 360
        elif d_h < -180:
            d_h += 360
        suma = h1p + h2p
        if abs(h1p - h2p) <= 180:
            h_media = suma / 2
        else:
            h_media = (suma + 360) / 2 if suma < 360 else (suma - 360) / 2
    d_hh = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(d_h / 2))
    l_media, cp_media = (l1 + l2) / 2, (c1p + c2p) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(h_media - 30))
        + 0.24 * math.cos(math.radians(2 * h_media))
        + 0.32 * math.cos(math.radians(3 * h_media + 6))
        - 0.20 * math.cos(math.radians(4 * h_media - 63))
    )
    giro = 30 * math.exp(-(((h_media - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_media**7 / (cp_media**7 + 25**7))
    s_l = 1 + 0.015 * (l_media - 50) ** 2 / math.sqrt(20 + (l_media - 50) ** 2)
    s_c = 1 + 0.045 * cp_media
    s_h = 1 + 0.015 * cp_media * t
    r_t = -math.sin(math.radians(2 * giro)) * r_c
    return math.sqrt(
        (d_l / s_l) ** 2 + (d_c / s_c) ** 2 + (d_hh / s_h) ** 2 + r_t * (d_c / s_c) * (d_hh / s_h)
    )


# ---------------------------------------------------------------------------- paleta


@dataclass(frozen=True)
class PaletaDibujo:
    """Brillo y color del dibujo: lo que el fondo no debe repetir."""

    luminosidad: float  # L* mediana de los trazos: 0 negro, 100 blanco
    croma: float  # C* mediana: 0 gris, 60+ muy saturado
    tono: float | None  # tono dominante en grados HSV (0 rojo, 60 amarillo...), None = gris
    color_medio: tuple[int, int, int]

    @property
    def familia(self) -> str:
        if self.tono is None:
            return "gris"
        t = self.tono
        if t < 40 or t >= 330:
            return "rojo"
        if t < 75:
            return "amarillo"
        if t < 165:
            return "verde"
        if t < 260:
            return "azul"
        return "morado"

    @property
    def claro(self) -> bool:
        return self.luminosidad >= 70

    @property
    def oscuro(self) -> bool:
        return self.luminosidad < 40


def _pixeles_opacos(dibujo: Image.Image) -> list[tuple[int, int, int]]:
    rgba = dibujo.convert("RGBA")
    rgba.thumbnail((_LADO_MEDIDA, _LADO_MEDIDA))
    return [(r, g, b) for r, g, b, a in rgba.getdata() if a >= 128]


def analizar(dibujo: Image.Image) -> PaletaDibujo:
    """Lee el dibujo recortado (RGBA). Los trazos de color pesan por su croma: el contorno
    negro de un pollito amarillo no lo vuelve «negro»."""
    pixeles = _pixeles_opacos(dibujo)
    if not pixeles:
        return PaletaDibujo(50.0, 0.0, None, (128, 128, 128))
    labs = [lab(p) for p in pixeles]
    cromas = [math.hypot(a, b) for _, a, b in labs]
    # Tono dominante: histograma de 24 casillas de 15°, cada píxel pesa su croma.
    casillas = [0.0] * 24
    for (r, g, b), c in zip(pixeles, cromas, strict=True):
        if c < _CROMA_GRIS:
            continue
        h = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360
        casillas[int(h // 15) % 24] += c
    coloreados = [i for i, c in enumerate(cromas) if c >= _CROMA_GRIS]
    tono: float | None = None
    # Si menos de un 15 % del dibujo tiene color, cuenta como gris (lápiz negro, gris).
    if len(coloreados) >= 0.15 * len(pixeles):
        # Suaviza con las vecinas para que 59° y 61° no compitan entre sí.
        suav = [casillas[i - 1] + 2 * casillas[i] + casillas[(i + 1) % 24] for i in range(24)]
        mejor = max(range(24), key=suav.__getitem__)
        tono = mejor * 15 + 7.5
    # El brillo que importa es el del relleno: si hay color, se mide sobre lo coloreado.
    base = coloreados if tono is not None else range(len(pixeles))
    luminosidad = median(labs[i][0] for i in base)
    croma = median(cromas[i] for i in base)
    n = len(base)
    color_medio = tuple(int(sum(pixeles[i][k] for i in base) / n) for k in range(3))
    return PaletaDibujo(round(luminosidad, 1), round(croma, 1), tono, color_medio)  # type: ignore[arg-type]


# Paletas de fondo que contrastan con cada familia de color y siguen viéndose naturales en un
# libro de cuentos (complementarios o vecinos suaves; nunca el mismo tono). Solo en positivo:
# flux-1-schnell no tiene prompt negativo y nombrar «sin amarillo» le hace pintar amarillo.
_CONTRASTES = {
    "rojo": "soft sky blue, cool teal green and pale aqua",
    "amarillo": "soft sky blue, cool blue-green and pale lilac",
    "verde": "warm sandy beige, soft peach, dusty lavender and pale blue-grey",
    "azul": "warm sandy yellow, soft peach, light ochre and pale coral",
    "morado": "fresh soft green, pale mint and light sandy yellow",
}


def guia_de_color(paleta: PaletaDibujo, reforzada: bool = False) -> str:
    """Fragmento en inglés para el prompt del fondo: paleta que contrasta y suelo despejado.

    `reforzada` es para el segundo intento, cuando el primer fondo no contrastó.
    """
    partes = []
    if paleta.familia in _CONTRASTES:
        colores = _CONTRASTES[paleta.familia]
        partes.append(
            f"The whole background is painted almost entirely in {colores}, including the ground"
            if reforzada
            else f"Background color palette: {colores}"
        )
    # Sin «character» ni «person»: nombrarlos hace que flux pinte uno (y a veces letras).
    if paleta.oscuro:
        partes.append("light, airy pastel tones")
    elif paleta.claro:
        partes.append("medium-deep, rich tones, not pale or washed out")
    else:
        partes.append("soft, slightly muted tones")
    partes.append("a wide, plain, empty patch of ground in the lower center foreground")
    return "; ".join(partes) + "."


# ---------------------------------------------------------------------------- medida


@dataclass(frozen=True)
class Colocacion:
    x: int
    y: int
    ancho: int
    alto: int


def _zona(fondo: Image.Image, dibujo: Image.Image, donde: Colocacion) -> tuple[list, list]:
    """Píxeles del dibujo y del fondo que queda justo detrás, a escala reducida."""
    escala = min(1.0, _LADO_MEDIDA / max(donde.ancho, donde.alto, 1))
    tam = (max(1, int(donde.ancho * escala)), max(1, int(donde.alto * escala)))
    detras = fondo.convert("RGB").crop(
        (donde.x, donde.y, donde.x + donde.ancho, donde.y + donde.alto)
    )
    # La textura fina del lápiz no cuenta: se mide el color de la zona.
    detras = detras.resize(tam, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1))
    delante = dibujo.convert("RGBA").resize(tam, Image.BILINEAR)
    pares = [
        (d[:3], f) for d, f in zip(delante.getdata(), detras.getdata(), strict=True) if d[3] >= 128
    ]
    return [p[0] for p in pares], [p[1] for p in pares]


def contraste(fondo: Image.Image, dibujo: Image.Image, donde: Colocacion) -> float:
    """Mediana de ΔE00 entre cada píxel del dibujo y el fondo detrás de él.

    ~2 es la diferencia mínima que nota el ojo; por debajo de ~20 el relleno del dibujo se
    confunde con el fondo aunque el contorno se vea.
    """
    delante, detras = _zona(fondo, dibujo, donde)
    if not delante:
        return 100.0
    return round(median(delta_e(lab(a), lab(b)) for a, b in zip(delante, detras, strict=True)), 1)


def _mascara_zona(lado: tuple[int, int], donde: Colocacion) -> Image.Image:
    """Elipse justa y difuminada alrededor del dibujo: la parte local de la corrección."""
    mascara = Image.new("L", lado, 0)
    margen_x, margen_y = int(donde.ancho * 0.12), int(donde.alto * 0.08)
    ImageDraw.Draw(mascara).ellipse(
        (
            donde.x - margen_x,
            donde.y - margen_y,
            donde.x + donde.ancho + margen_x,
            donde.y + donde.alto + margen_y,
        ),
        fill=255,
    )
    return mascara.filter(ImageFilter.GaussianBlur(max(16, donde.ancho // 6)))


def _tinte_contrario(paleta: PaletaDibujo, claridad: float) -> tuple[int, int, int]:
    """Color suave del lado opuesto del círculo cromático al del dibujo."""
    if paleta.tono is None:
        tono = 220.0 if paleta.luminosidad >= 55 else 45.0  # gris: sombra fría o luz cálida
    else:
        tono = (paleta.tono + 180) % 360
    r, g, b = colorsys.hls_to_rgb(tono / 360, claridad, 0.35)
    return int(r * 255), int(g * 255), int(b * 255)


def _version_contrastada(
    fondo: Image.Image, paleta: PaletaDibujo, intensa: bool = False
) -> Image.Image:
    """El mismo fondo con su textura, algo menos saturado y teñido hacia el color contrario.

    Dibujo claro (amarillo, blanco, pastel): una sombra fría del color complementario (un
    pollito amarillo queda sobre un tono lila). Dibujo oscuro: un claro de luz cálida. Se ve
    como luz de la escena, no como una mancha gris.
    """
    rgb = ImageEnhance.Color(fondo.convert("RGB")).enhance(0.4 if intensa else 0.7)
    if paleta.luminosidad >= 55:
        tinte = _tinte_contrario(paleta, 0.58 if intensa else 0.72)
        return ImageChops.multiply(rgb, Image.new("RGB", rgb.size, tinte))
    tinte = _tinte_contrario(paleta, 0.7 if intensa else 0.55)
    return ImageChops.screen(rgb, Image.new("RGB", rgb.size, tinte))


def armonizar_fondo(
    fondo: Image.Image,
    dibujo: Image.Image,
    donde: Colocacion,
    paleta: PaletaDibujo,
    minimo: float = CONTRASTE_MINIMO,
) -> tuple[Image.Image, float, float]:
    """Corrige lo justo hasta llegar al contraste mínimo, como un cambio de luz de la escena.

    La mitad de la fuerza va a todo el fondo (todo el paisaje toma la misma luz, así no queda
    una mancha) y la fuerza entera solo alrededor del dibujo. Sube por pasos y se detiene en
    cuanto alcanza. Devuelve el fondo (el mismo si ya alcanzaba), el contraste inicial y el
    final.
    """
    actual = contraste(fondo, dibujo, donde)
    if actual >= minimo:
        return fondo, actual, actual
    rgb = fondo.convert("RGB")
    suave = _version_contrastada(rgb, paleta)
    mascara = _mascara_zona(rgb.size, donde)
    mejor, mejor_c = rgb, actual
    # El último paso, más intenso, solo llega cuando el fondo es casi del color del dibujo.
    pasos = [(suave, 0.35), (suave, 0.6), (suave, 0.85), (suave, 1.0)]
    pasos.append((_version_contrastada(rgb, paleta, intensa=True), 1.0))
    for contrastado, fuerza in pasos:
        global_y_local = ImageChops.lighter(
            Image.new("L", rgb.size, int(255 * fuerza * 0.5)),
            mascara.point(lambda v, f=fuerza: int(v * f)),
        )
        candidata = Image.composite(contrastado, rgb, global_y_local)
        c = contraste(candidata, dibujo, donde)
        if c > mejor_c:
            mejor, mejor_c = candidata, c
        if c >= minimo:
            break
    return mejor, actual, mejor_c


# ---------------------------------------------------------------------------- integración


def luz_de_escena(fondo: Image.Image) -> tuple[int, int, int]:
    """Color medio del fondo: el tono de la luz que baña la escena."""
    pequeno = fondo.convert("RGB").resize((1, 1), Image.BOX)
    return pequeno.getpixel((0, 0))  # type: ignore[return-value]


def ajustar_a_la_luz(dibujo: Image.Image, luz: tuple[int, int, int], fuerza: float = 0.14):
    """Tiñe muy poco el dibujo con la luz de la escena (multiplicar a ~14 %): sigue siendo
    el dibujo del niño, pero deja de verse «recortado» de otra foto."""
    rgba = dibujo.convert("RGBA")
    maximo = max(max(luz), 1)
    tinte = tuple(int(255 - (255 - c * 255 / maximo) * fuerza) for c in luz)
    color = ImageChops.multiply(rgba.convert("RGB"), Image.new("RGB", rgba.size, tinte))
    color.putalpha(rgba.getchannel("A"))
    return color


def suavizar_borde(dibujo: Image.Image) -> Image.Image:
    """Quita el halo blanco del recorte (1 px hacia dentro) y difumina apenas el borde."""
    rgba = dibujo.convert("RGBA")
    alfa = (
        rgba.getchannel("A").filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    )
    rgba.putalpha(alfa)
    return rgba


def sombra_de_contacto(
    dibujo: Image.Image, donde: Colocacion, luz: tuple[int, int, int]
) -> tuple[Image.Image, tuple[int, int]]:
    """Una sombra suave bajo la base del dibujo, del color oscuro de la escena (no negra).

    Devuelve la capa (solo del tamaño de la sombra, para difuminar poco) y dónde va.
    """
    alfa = dibujo.getchannel("A")
    # Ancho de la base: lo opaco en el 15 % inferior del dibujo.
    franja = alfa.crop((0, int(alfa.height * 0.85), alfa.width, alfa.height)).getbbox()
    izq, der = (franja[0], franja[2]) if franja else (0, alfa.width)
    base_ancho = max(der - izq, alfa.width * 0.3)
    rx, ry = base_ancho * 0.62, max(10.0, donde.alto * 0.045)
    radio = max(6.0, ry * 0.9)
    margen = int(radio * 3)
    ancho, alto = int(2 * rx) + 2 * margen, int(2 * ry) + 2 * margen
    capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    oscuro = tuple(int(c * 0.35) for c in luz)
    ImageDraw.Draw(capa).ellipse(
        (margen, margen, margen + 2 * rx, margen + 2 * ry), fill=(*oscuro, 150)
    )
    cx = donde.x + (izq + der) / 2
    pie = donde.y + donde.alto
    # La elipse queda centrada un poco por encima del pie: el dibujo «pisa» la sombra.
    destino = (int(cx - rx) - margen, int(pie - ry * 1.2) - margen)
    return capa.filter(ImageFilter.GaussianBlur(radio)), destino


@lru_cache(maxsize=2)
def _textura(lado: int) -> Image.Image:
    """Grano de papel y rayado de lápiz, siempre igual (semilla fija). Gris medio = neutro."""
    grano = Image.effect_noise((lado, lado), 22).filter(ImageFilter.GaussianBlur(0.6))
    rayado = Image.new("L", (lado, lado), 128)
    dib = ImageDraw.Draw(rayado)
    azar = random.Random(20261109)  # noqa: S311 - textura con semilla fija, no criptografía
    for _ in range(lado * 3):
        x, y = azar.randrange(-lado, lado), azar.randrange(0, lado)
        largo = azar.randrange(lado // 40, lado // 12)
        tono = 128 + azar.choice((-1, 1)) * azar.randrange(10, 26)
        dib.line((x + y, y, x + y + largo, y - largo), fill=tono, width=1)
    rayado = rayado.filter(ImageFilter.GaussianBlur(0.7))
    return Image.blend(grano, rayado, 0.5).convert("RGB")


def textura_de_lapiz(pagina: Image.Image, fuerza: float = 0.55) -> Image.Image:
    """La misma textura de papel y lápiz por encima de todo (fondo y dibujo) para unificar."""
    rgb = pagina.convert("RGB")
    textura = _textura(rgb.width)
    if textura.size != rgb.size:
        textura = textura.resize(rgb.size)
    return Image.blend(rgb, ImageChops.soft_light(rgb, textura), fuerza)
