"""Lo que la escena de cada página dice antes de pedir el fondo: ambiente y colores del lugar.

Tres decisiones (segunda vuelta de los fondos, 2026-11-09, «dale esos ajustes a fors»):

1. **Ambiente primero** (`ambiente_de`): la escena (en inglés, la escribe el modelo del cuento)
   dice si es de día, al atardecer, de noche, bajo el agua o bajo techo. La paleta que contrasta
   con el dibujo se elige *dentro* de ese ambiente y la corrección de luz no lo cambia: la noche
   sigue siendo noche y el dibujo oscuro se destaca con una zona iluminada, no volviendo de día.
2. **El color del lugar** (`recolorear_escena`, `recolorear_texto`): si la escena nombra para el
   lugar el mismo color del dibujo («golden wheat field» con un pollito amarillo), se cambia ese
   color en la descripción visual antes de pedir el fondo («fresh green wheat field»). El texto
   que lee el niño solo cambia si dice explícitamente ese color *del lugar* («el trigal dorado»
   → «el trigal verde»), para que lo que lee y lo que ve coincidan; nunca se toca un color que
   no siga a un sustantivo de lugar (el «pollito amarillo» queda igual).
   - Choque = el color nombrado es de la misma familia de tono que el dibujo (amarillo, rojo,
     verde, azul, morado). Un dibujo gris, negro o blanco no choca por tono: se resuelve con luz.
   - El reemplazo depende de qué cosa pinta: suelo y plantas, cielo y agua, arena, edificios o
     corales. Siempre dentro del mismo ambiente (un cielo azul de día pasa a «pale misty», no a
     un cielo de atardecer).
   - Se respetan las fuentes de luz pequeñas (sol, luna, estrellas, faroles, ventanas): un sol
     amarillo no se cambia.
3. **Lo que vuela o nada** (`en_el_aire`): aves, peces, insectos voladores, nubes, aviones,
   globos… no llevan sombra de contacto ni se apoyan en el suelo. Se decide con lo que ya sabe el
   pipeline: el personaje (lo dijo el niño o la visión) y el ambiente (bajo el agua, todo nada).

Todo es texto local, sin IA ni red: barato, determinista y fácil de probar.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

Ambiente = Literal["dia", "atardecer", "noche", "bajo_agua", "interior"]
Familia = Literal["rojo", "amarillo", "verde", "azul", "morado", "gris"]

# ---------------------------------------------------------------------------- ambiente

# El orden importa: bajo el agua gana (un arrecife «at night» sigue siendo agua), luego la noche
# (una habitación de noche es oscura), el atardecer y el interior. Lo demás es de día.
_PISTAS_AMBIENTE: tuple[tuple[Ambiente, tuple[str, ...]], ...] = (
    (
        "bajo_agua",
        (
            "underwater",
            "under the sea",
            "under the ocean",
            "under water",
            "beneath the waves",
            "coral reef",
            "seabed",
            "sea floor",
            "seafloor",
            "ocean floor",
            "deep sea",
            "bajo el agua",
            "bajo el mar",
            "fondo del mar",
        ),
    ),
    (
        "noche",
        (
            "night",
            "midnight",
            "moonlight",
            "moonlit",
            "starry",
            "starlit",
            "full moon",
            "crescent moon",
            "dark sky",
            "noche",
            "luna llena",
            "estrellas",
        ),
    ),
    (
        "atardecer",
        (
            "sunset",
            "dusk",
            "twilight",
            "evening",
            "sunrise",
            "dawn",
            "golden hour",
            "atardecer",
            "anochecer",
            "amanecer",
        ),
    ),
    (
        "interior",
        (
            "inside",
            "indoors",
            "bedroom",
            "living room",
            "kitchen",
            "classroom",
            "library",
            "cave",
            "attic",
            "a room",
            "cozy room",
            "hall",
            "habitación",
            "cueva",
            "cocina",
        ),
    ),
)


def _normal(texto: str) -> str:
    return texto.lower()


def ambiente_de(escena: str, texto: str = "") -> Ambiente:
    """Hora y lugar de la luz de una página. Primero la escena; si no dice nada, el texto."""
    for fuente in (escena, texto):
        bajo = _normal(fuente)
        for ambiente, pistas in _PISTAS_AMBIENTE:
            if any(re.search(rf"\b{re.escape(p)}", bajo) for p in pistas):
                return ambiente
    return "dia"


# ---------------------------------------------------------------------------- vuela o nada

_VUELA_O_NADA = (
    # aves e insectos voladores
    "pájaro",
    "pajaro",
    "pajarito",
    "ave",
    "aves",
    "loro",
    "perico",
    "búho",
    "buho",
    "lechuza",
    "águila",
    "aguila",
    "halcón",
    "paloma",
    "colibrí",
    "colibri",
    "gaviota",
    "golondrina",
    "tucán",
    "tucan",
    "mariposa",
    "abeja",
    "abejita",
    "libélula",
    "libelula",
    "luciérnaga",
    "luciernaga",
    "mariquita voladora",
    "murciélago",
    "murcielago",
    # lo que nada
    "pez",
    "peces",
    "pececito",
    "pescado",
    "tiburón",
    "tiburon",
    "ballena",
    "delfín",
    "delfin",
    "medusa",
    "pulpo",
    "caballito de mar",
    "sirena",
    "submarino",
    # cielo y lo que flota
    "nube",
    "nubecita",
    "avión",
    "avion",
    "avioneta",
    "helicóptero",
    "helicoptero",
    "cohete",
    "nave espacial",
    "ovni",
    "globo",
    "cometa",
    "dron",
    "hada",
    "fantasma",
    "estrella",
    "luna",
    "sol",
    "arcoíris",
    "arcoiris",
    # por si el niño lo escribe en inglés
    "bird",
    "fish",
    "butterfly",
    "bee",
    "cloud",
    "plane",
    "airplane",
    "rocket",
    "balloon",
    "kite",
    "whale",
    "dolphin",
    "shark",
    "jellyfish",
)
# Bajo el agua todo nada, salvo lo que camina por el fondo.
_CAMINA_BAJO_EL_AGUA = ("cangrejo", "caracol", "estrella de mar", "langosta")


def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def en_el_aire(personaje: str, ambiente: Ambiente) -> bool:
    """True si el protagonista vuela o nada: sin sombra de contacto ni suelo bajo él."""
    nombre = _sin_tildes(_normal(personaje))
    if ambiente == "bajo_agua":
        return not any(re.search(rf"\b{_sin_tildes(p)}", nombre) for p in _CAMINA_BAJO_EL_AGUA)
    # «estrella de mar» camina; «sol» no debe saltar con «soldado»: palabra entera.
    if "estrella de mar" in nombre:
        return False
    return any(re.search(rf"\b{re.escape(_sin_tildes(p))}\b", nombre) for p in _VUELA_O_NADA)


# ---------------------------------------------------------------------------- color del lugar

Clase = Literal["suelo", "cielo", "arena", "edificio", "coral"]

# Palabras de color en inglés y su familia de tono (la misma de `PaletaDibujo.familia`).
_COLORES_EN: dict[str, Familia] = {
    "yellow": "amarillo",
    "golden": "amarillo",
    "gold": "amarillo",
    "amber": "amarillo",
    "lemon": "amarillo",
    "mustard": "amarillo",
    "sunflower": "amarillo",
    "red": "rojo",
    "crimson": "rojo",
    "scarlet": "rojo",
    "ruby": "rojo",
    "cherry": "rojo",
    "orange": "rojo",
    "tangerine": "rojo",
    "rust": "rojo",
    "pink": "rojo",
    "green": "verde",
    "emerald": "verde",
    "lime": "verde",
    "olive": "verde",
    "mint": "verde",
    "blue": "azul",
    "azure": "azul",
    "navy": "azul",
    "turquoise": "azul",
    "teal": "azul",
    "cyan": "azul",
    "aqua": "azul",
    "purple": "morado",
    "violet": "morado",
    "lilac": "morado",
    "lavender": "morado",
    "magenta": "morado",
    "plum": "morado",
}
_MATICES_EN = ("light", "dark", "deep", "bright", "pale", "soft", "vivid", "warm", "cool")

_CLASES_EN: dict[Clase, tuple[str, ...]] = {
    "cielo": (
        "sky",
        "skies",
        "cloud",
        "clouds",
        "water",
        "sea",
        "ocean",
        "lake",
        "river",
        "pond",
        "waves",
        "air",
    ),
    "arena": ("sand", "sandy", "beach", "desert", "dune", "dunes"),
    "edificio": (
        "house",
        "houses",
        "wall",
        "walls",
        "barn",
        "roof",
        "roofs",
        "door",
        "doors",
        "building",
        "buildings",
        "castle",
        "tower",
        "fence",
    ),
    "coral": ("coral", "corals", "reef", "seaweed", "anemone", "anemones"),
}
# Fuentes de luz pequeñas: su color no tapa al dibujo y cambiarlo se vería raro.
_LUCES_EN = (
    "sun",
    "sunshine",
    "sunlight",
    "moon",
    "star",
    "stars",
    "lamp",
    "lamps",
    "lamppost",
    "lampposts",
    "lantern",
    "lanterns",
    "window",
    "windows",
    "light",
    "lights",
    "glow",
    "candle",
    "candles",
    "fireflies",
)

# Reemplazo en inglés por familia del dibujo y clase de lo pintado. Dos opciones para cuando la
# escena nombra dos colores de la misma familia seguidos («red and orange corals»).
_REEMPLAZO_EN: dict[Familia, dict[Clase, tuple[str, str]]] = {
    "amarillo": {
        "suelo": ("fresh green", "soft blue-green"),
        "cielo": ("soft blue", "pale lilac"),
        "arena": ("pale silver-grey", "soft grey-blue"),
        "edificio": ("soft blue", "pale lilac"),
        "coral": ("violet", "soft blue"),
    },
    "rojo": {
        "suelo": ("fresh green", "soft blue-green"),
        "cielo": ("soft blue", "pale aqua"),
        "arena": ("pale sandy beige", "soft grey"),
        "edificio": ("soft teal", "pale blue"),
        "coral": ("teal", "aqua"),
    },
    "verde": {
        "suelo": ("warm golden", "soft peach"),
        "cielo": ("pale blue-grey", "soft peach"),
        "arena": ("warm sandy", "soft peach"),
        "edificio": ("warm peach", "dusty lavender"),
        "coral": ("coral pink", "soft lavender"),
    },
    "azul": {
        "suelo": ("warm golden", "soft peach"),
        # Un cielo o un mar azul definen el día: se aclaran sin volverlos de otro color.
        "cielo": ("pale misty", "pale hazy"),
        "arena": ("warm sandy", "light ochre"),
        "edificio": ("warm peach", "light ochre"),
        "coral": ("coral pink", "warm peach"),
    },
    "morado": {
        "suelo": ("fresh green", "pale mint"),
        "cielo": ("pale golden", "soft mint"),
        "arena": ("warm sandy", "pale yellow"),
        "edificio": ("soft green", "pale yellow"),
        "coral": ("mint green", "pale yellow"),
    },
}

_RE_COLOR_EN = re.compile(
    r"\b(?:(?:" + "|".join(_MATICES_EN) + r")[\s-]+)?(" + "|".join(_COLORES_EN) + r")\b",
    re.I,
)


def _clase_en(resto: str) -> Clase | None:
    """La clase de lo que pinta el color, mirando las 4 palabras que lo siguen.

    None = es una fuente de luz pequeña (sol, luna, ventana): no se cambia.
    """
    palabras = re.findall(r"[a-z]+", resto.lower())[:4]
    for palabra in palabras:
        if palabra in _LUCES_EN:
            return None
        for clase, nombres in _CLASES_EN.items():
            if palabra in nombres:
                return clase
    return "suelo"


def recolorear_escena(escena: str, familia: Familia) -> tuple[str, list[tuple[str, str]]]:
    """Cambia en la escena (inglés) los colores del lugar que chocan con el dibujo.

    Devuelve la escena nueva y la lista de cambios (antes, después), para el log y las pruebas.
    """
    if familia not in _REEMPLAZO_EN:
        return escena, []
    cambios: list[tuple[str, str]] = []
    usados: dict[Clase, int] = {}

    def cambiar(m: re.Match) -> str:
        if _COLORES_EN[m.group(1).lower()] != familia:
            return m.group(0)
        clase = _clase_en(escena[m.end() :])
        if clase is None:
            return m.group(0)
        opciones = _REEMPLAZO_EN[familia][clase]
        nuevo = opciones[min(usados.get(clase, 0), 1)]
        usados[clase] = usados.get(clase, 0) + 1
        cambios.append((m.group(0), nuevo))
        return nuevo

    nueva = _RE_COLOR_EN.sub(cambiar, escena)
    # «green and green», «soft blue, soft blue»: si quedó repetido, sobra uno.
    nueva = re.sub(r"\b([\w-]+(?: [\w-]+)?)(?: and |, | or )\1\b", r"\1", nueva)
    return nueva, cambios


# Español: sustantivo de lugar seguido de su color («el trigal dorado», «corales rojos»).
# (género, clase); el plural se reconoce por la -s del color.
_LUGARES_ES: dict[str, tuple[Literal["m", "f"], Clase]] = {
    "trigo": ("m", "suelo"),
    "trigal": ("m", "suelo"),
    "trigales": ("m", "suelo"),
    "campo": ("m", "suelo"),
    "campos": ("m", "suelo"),
    "prado": ("m", "suelo"),
    "prados": ("m", "suelo"),
    "pradera": ("f", "suelo"),
    "praderas": ("f", "suelo"),
    "colina": ("f", "suelo"),
    "colinas": ("f", "suelo"),
    "pasto": ("m", "suelo"),
    "hierba": ("f", "suelo"),
    "césped": ("m", "suelo"),
    "valle": ("m", "suelo"),
    "bosque": ("m", "suelo"),
    "selva": ("f", "suelo"),
    "jardín": ("m", "suelo"),
    "hojas": ("f", "suelo"),
    "cielo": ("m", "cielo"),
    "mar": ("m", "cielo"),
    "agua": ("f", "cielo"),
    "lago": ("m", "cielo"),
    "río": ("m", "cielo"),
    "océano": ("m", "cielo"),
    "arena": ("f", "arena"),
    "playa": ("f", "arena"),
    "desierto": ("m", "arena"),
    "dunas": ("f", "arena"),
    "casa": ("f", "edificio"),
    "casas": ("f", "edificio"),
    "pared": ("f", "edificio"),
    "paredes": ("f", "edificio"),
    "granero": ("m", "edificio"),
    "castillo": ("m", "edificio"),
    "techo": ("m", "edificio"),
    "techos": ("m", "edificio"),
    "coral": ("m", "coral"),
    "corales": ("m", "coral"),
}

_COLORES_ES: dict[str, Familia] = {
    "amarill": "amarillo",
    "dorad": "amarillo",
    "roj": "rojo",
    "rojiz": "rojo",
    "anaranjad": "rojo",
    "naranja": "rojo",
    "rosad": "rojo",
    "verde": "verde",
    "azul": "azul",
    "celeste": "azul",
    "morad": "morado",
    "violeta": "morado",
    "lila": "morado",
}
_RE_COLOR_ES = re.compile(
    r"\b(" + "|".join(sorted(_LUGARES_ES, key=len, reverse=True)) + r")\s+"
    r"(amarill[oa]s?|dorad[oa]s?|roj[oa]s?|rojiz[oa]s?|anaranjad[oa]s?|naranjas?|rosad[oa]s?"
    r"|verdes?|azul(?:es)?|celestes?|morad[oa]s?|violetas?|lilas?)\b",
    re.I,
)

# (masculino, femenino) en singular; None = no hay un cambio natural y el texto queda igual.
_REEMPLAZO_ES: dict[Familia, dict[Clase, tuple[str, str] | None]] = {
    "amarillo": {
        "suelo": ("verde", "verde"),
        "cielo": ("azul", "azul"),
        "arena": ("gris", "gris"),
        "edificio": ("azul", "azul"),
        "coral": ("violeta", "violeta"),
    },
    "rojo": {
        "suelo": ("verde", "verde"),
        "cielo": ("azul", "azul"),
        "arena": None,
        "edificio": ("azul", "azul"),
        "coral": ("turquesa", "turquesa"),
    },
    "verde": {
        "suelo": ("dorado", "dorada"),
        "cielo": ("claro", "clara"),
        "arena": None,
        "edificio": None,
        "coral": ("rosado", "rosada"),
    },
    "azul": {
        "suelo": ("dorado", "dorada"),
        "cielo": ("claro", "clara"),
        "arena": None,
        "edificio": None,
        "coral": ("rosado", "rosada"),
    },
    "morado": {
        "suelo": ("verde", "verde"),
        "cielo": ("dorado", "dorada"),
        "arena": None,
        "edificio": ("verde", "verde"),
        "coral": ("verde", "verde"),
    },
}


def _familia_es(color: str) -> Familia | None:
    bajo = color.lower()
    for raiz, familia in _COLORES_ES.items():
        if bajo.startswith(raiz):
            return familia
    return None


def _plural(palabra: str) -> str:
    return palabra + ("s" if palabra[-1] in "aeiou" else "es")


def recolorear_texto(texto: str, familia: Familia) -> tuple[str, list[tuple[str, str]]]:
    """Cambia en el texto del niño el color *del lugar* cuando choca con el dibujo.

    Solo «sustantivo de lugar + color» («el trigal dorado» → «el trigal verde»), con el género
    y el número del sustantivo. Un color que no sigue a un lugar no se toca.
    """
    reemplazos = _REEMPLAZO_ES.get(familia)
    if not reemplazos:
        return texto, []
    cambios: list[tuple[str, str]] = []

    def cambiar(m: re.Match) -> str:
        lugar, color = m.group(1), m.group(2)
        if _familia_es(color) != familia:
            return m.group(0)
        genero, clase = _LUGARES_ES[lugar.lower()]
        opcion = reemplazos.get(clase)
        if opcion is None:
            return m.group(0)
        nuevo = opcion[0] if genero == "m" else opcion[1]
        if color.lower().endswith("s"):
            nuevo = _plural(nuevo)
        if color[0].isupper():
            nuevo = nuevo.capitalize()
        cambios.append((color, nuevo))
        return f"{lugar} {nuevo}"

    return _RE_COLOR_ES.sub(cambiar, texto), cambios
