"""Lo que comparten los adaptadores de LLM: prompts, esquemas JSON y lectura de respuestas.

Los usan OpenAI, Cloudflare Workers AI y Ollama, para que el cuento pida lo mismo a
cualquier proveedor y se lea igual.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from app.dominio.puertos import (
    AtributosDibujo,
    CuentoTexto,
    Hipotesis,
    PaginaTexto,
    SolicitudCuento,
    Uso,
)


class ErrorProveedor(RuntimeError):
    """El proveedor respondió con error o con algo ilegible. El orquestador reintenta."""


class MotorChatJSON(Protocol):
    """Un LLM al que se le pide JSON con un esquema (Ollama o Cloudflare Workers AI)."""

    proveedor: str

    @property
    def timeout_s(self) -> float | None: ...

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
    ) -> tuple[dict, Uso]: ...


ESQUEMA_VISION = {
    "name": "identificacion_dibujo",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "hipotesis": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "etiqueta": {"type": "string"},
                        "confianza": {"type": "number"},
                    },
                    "required": ["etiqueta", "confianza"],
                },
            },
            # Rasgos visibles del dibujo: el cuento los usa para no inventar otros.
            "atributos": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "colores": {"type": "array", "items": {"type": "string"}},
                    "elementos": {"type": "array", "items": {"type": "string"}},
                    "emocion": {"type": "string"},
                },
                "required": ["colores", "elementos", "emocion"],
            },
        },
        "required": ["hipotesis", "atributos"],
    },
}

PAGINAS_CUENTO = 3

ESQUEMA_CUENTO = {
    "name": "cuento_infantil",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "titulo": {"type": "string"},
            "paginas": {
                "type": "array",
                # Exactamente 3: con Ollama el esquema se vuelve gramática y el modelo no
                # puede cerrar el arreglo antes; el dominio lo valida igual por si acaso.
                "minItems": PAGINAS_CUENTO,
                "maxItems": PAGINAS_CUENTO,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "texto": {"type": "string"},
                        "escena": {"type": "string"},
                    },
                    "required": ["texto", "escena"],
                },
            },
        },
        "required": ["titulo", "paginas"],
    },
}

PROMPT_VISION = (
    "Eres un asistente amable que mira dibujos hechos por niños de 6 a 12 años. "
    "Di qué personaje u objeto principal dibujó el niño. Devuelve de 2 a 4 hipótesis "
    "distintas, en español, de 1 a 3 palabras cada una (por ejemplo «un perro», «un "
    "dragón»), con una confianza entre 0 y 1. Sé generoso: es un dibujo infantil, no "
    "una foto. Nunca describas a personas reales ni datos personales.\n"
    "En «atributos» describe solo lo que se ve en el dibujo, en español y en minúsculas: "
    "«colores» (de 1 a 4 colores principales del personaje), «elementos» (de 0 a 5 partes "
    "o cosas visibles, como «cola larga», «alas», «sol») y «emocion» (una palabra, como "
    "«alegre»). No inventes nada que no esté dibujado."
)

PROMPT_CUENTO = (
    "Eres un autor de cuentos infantiles en español. Escribe un cuento para un niño de "
    "{edad} años cuyo protagonista es {personaje}, tal como lo dibujó el niño.\n"
    "Reglas:\n"
    "1. Exactamente {paginas} páginas, de 40 a 70 palabras cada una, "
    "con inicio, nudo y final feliz.\n"
    "2. Vocabulario adecuado a la edad; frases cortas; tono cálido.\n"
    "3. Nada de violencia, miedo intenso, armas, sustancias, romance ni marcas comerciales.\n"
    "4. El protagonista no cambia de forma ni de nombre.\n"
    "5. En «escena», describe en inglés solo el fondo de esa página, sin personajes, "
    "personas, animales ni texto. El fondo debe ser el lugar donde el protagonista vive o "
    "se usa de forma natural, para que dibujo y fondo tengan sentido juntos: un carro en "
    "una carretera, un pez en el mar, un animal de la selva en la selva, un martillo en "
    "una obra de construcción, un barco en el mar, un avión en el cielo. Si el "
    "protagonista es un objeto o vehículo, el lugar puede ser urbano o de obra, pero "
    "siempre vacío de gente. Si no está claro, elige un paisaje natural sencillo. Todas "
    "las páginas ocurren en ese mismo lugar (puedes variar la hora o el rincón) y mantén "
    "la misma paleta de colores para que el estilo sea coherente.\n"
    "6. {rasgos}\n"
    "7. {nombre}"
)

_RASGOS_CONOCIDOS = (
    "Así es el protagonista en el dibujo ({atributos}). Descríbelo solo con esos rasgos: "
    "no inventes otros colores, pelaje, ropa ni partes que no estén en el dibujo."
)
_REGLA_NOMBRE = (
    "El niño le puso nombre al protagonista: se llama «{nombre}». Llámalo siempre por ese "
    "nombre en el título y en todas las páginas, como un nombre propio."
)
_RASGOS_DESCONOCIDOS = (
    "No conoces los colores ni los rasgos del dibujo: no los describas ni los inventes."
)


ESQUEMA_MODERACION = {
    "name": "moderacion_infantil",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "apto": {"type": "boolean"},
            "categorias": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["apto", "categorias"],
    },
}

PROMPT_MODERACION = (
    "Eres un moderador de contenido para una app de cuentos para niños de 6 a 12 años. "
    "Lee el texto del usuario y decide si es apto para esa edad. NO es apto si tiene "
    "violencia, sangre, armas, muerte, miedo intenso, contenido sexual o romántico, "
    "drogas, alcohol, tabaco, autolesiones, odio, insultos, burlas, datos personales "
    "(direcciones, teléfonos, nombres completos) o marcas comerciales. Si dudas, NO es apto. "
    'Responde solo JSON: {"apto": true|false, "categorias": ["..."]}, con las categorías '
    "incumplidas en minúsculas (lista vacía si es apto)."
)


def prompt_fondo(descripcion: str) -> str:
    """Prompt de fondo para cualquier proveedor de imagen: estilo lápices de colores y
    crayón de libro de cuentos (elegido por Josue el 2026-10-22), sin fotorrealismo."""
    return (
        "Colored pencil and crayon illustration from a children's storybook, hand-drawn "
        "outlines, simple shapes, bright cheerful colors, grainy paper texture, flat 2D "
        "naive style like a picture book, not photorealistic, not 3D. "
        f"Scene: {descripcion}. No characters, no people, no animals, no text, no letters."
    )


def mensaje_cuento(
    personaje: str,
    edad: int,
    paginas: int,
    atributos: AtributosDibujo | None = None,
    nombre: str = "",
) -> str:
    if atributos is not None and not atributos.vacio:
        rasgos = _RASGOS_CONOCIDOS.format(atributos=atributos.como_texto())
    else:
        rasgos = _RASGOS_DESCONOCIDOS
    nombre = nombre.strip()
    regla_nombre = (
        _REGLA_NOMBRE.format(nombre=nombre) if nombre else "No tiene nombre: llámalo por lo que es."
    )
    return PROMPT_CUENTO.format(
        edad=edad, personaje=personaje, paginas=paginas, rasgos=rasgos, nombre=regla_nombre
    )


def mensaje_solicitud(solicitud: SolicitudCuento) -> str:
    return mensaje_cuento(
        solicitud.personaje,
        solicitud.edad,
        solicitud.paginas,
        solicitud.atributos,
        solicitud.nombre,
    )


def leer_json(contenido: object) -> dict:
    """Acepta un dict ya parseado o un texto con JSON (tolera bloques ```json de modelos
    pequeños). Si no hay un objeto JSON válido, lanza ValueError."""
    if isinstance(contenido, dict):
        return contenido
    if not isinstance(contenido, str) or not contenido.strip():
        raise ValueError("respuesta vacía")
    texto = contenido.strip()
    cercado = re.search(r"```(?:json)?\s*(\{.*\})\s*```", texto, re.S)
    if cercado:
        texto = cercado.group(1)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio < 0 or fin <= inicio:
            raise ValueError("la respuesta no es JSON") from None
        datos = json.loads(texto[inicio : fin + 1])
    if not isinstance(datos, dict):
        raise ValueError("la respuesta no es un objeto JSON")
    return datos


def hipotesis_desde(datos: dict) -> list[Hipotesis]:
    return [
        Hipotesis(str(h["etiqueta"]), float(h["confianza"]))
        for h in datos.get("hipotesis", [])
        if isinstance(h, dict) and "etiqueta" in h and "confianza" in h
    ]


def _textos(valor: object, maximo: int) -> tuple[str, ...]:
    if not isinstance(valor, list):
        return ()
    limpios = [str(v).strip()[:30] for v in valor if isinstance(v, str | int | float)]
    return tuple(dict.fromkeys(v for v in limpios if v))[:maximo]


def atributos_desde(datos: dict) -> AtributosDibujo:
    """Lee los rasgos del dibujo con topes de cantidad y largo. Si faltan, quedan vacíos."""
    crudos = datos.get("atributos")
    if not isinstance(crudos, dict):
        return AtributosDibujo()
    emocion = crudos.get("emocion")
    return AtributosDibujo(
        colores=_textos(crudos.get("colores"), 4),
        elementos=_textos(crudos.get("elementos"), 5),
        emocion=emocion.strip()[:30] if isinstance(emocion, str) else "",
    )


def cuento_desde(datos: dict, uso: Uso) -> CuentoTexto:
    paginas = [
        PaginaTexto(str(p["texto"]), str(p.get("escena", "")))
        for p in datos.get("paginas", [])
        if isinstance(p, dict) and p.get("texto")
    ]
    return CuentoTexto(str(datos.get("titulo", "")), paginas, uso)


def veredicto_desde(datos: dict) -> tuple[bool, list[str]]:
    """Falla cerrada: solo `apto: true` (booleano) aprueba; si falta el campo, lanza."""
    if "apto" not in datos:
        raise ErrorProveedor("la moderación no devolvió «apto»")
    categorias = [str(c) for c in datos.get("categorias") or [] if str(c).strip()]
    aprobado = datos["apto"] is True
    if not aprobado and not categorias:
        categorias = ["no_apto"]
    return aprobado, categorias
