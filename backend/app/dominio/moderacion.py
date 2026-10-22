"""Moderación de contenido: obligatoria y sin interruptor.

No existe ninguna variable, parámetro ni bandera que la desactive. El orquestador la
recibe en su constructor y no tiene camino que la salte. Si el proveedor de moderación
falla, el contenido se considera NO aprobado (falla cerrada).
"""

from __future__ import annotations

import re
import unicodedata

from app.dominio.puertos import IModerador, Uso, VeredictoModeracion

# Primer filtro local, barato y sin red. No sustituye al proveedor: lo complementa.
# Cada término es una expresión que debe coincidir con una palabra completa.
_TERMINOS_BLOQUEADOS = (
    r"sangr\w*",
    r"matar\w*|mataron|matando",
    r"muerte",
    r"muert[oa]s?",
    r"asesin\w*",
    r"armas?",
    r"pistolas?",
    r"cuchill\w*",
    r"drogas?",
    r"alcohol",
    r"cervezas?",
    r"cigarr\w*",
    r"sexo\w*",
    r"desnud\w*",
    r"suicid\w*",
    r"odi[oa]r?",
    r"estupid[oa]s?",
    r"idiotas?",
)


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.lower()


class Moderacion:
    def __init__(self, moderador: IModerador, terminos: tuple[str, ...] = _TERMINOS_BLOQUEADOS):
        self._moderador = moderador
        self._patron = re.compile(r"\b(" + "|".join(f"(?:{t})" for t in terminos) + r")\b")

    def revisar_local(self, texto: str) -> VeredictoModeracion:
        hallados = sorted({m.group(1) for m in self._patron.finditer(_normalizar(texto))})
        if hallados:
            return VeredictoModeracion(False, [f"local:{t}" for t in hallados], Uso())
        return VeredictoModeracion(True, [], Uso())

    async def revisar(self, texto: str) -> VeredictoModeracion:
        local = self.revisar_local(texto)
        if not local.aprobado:
            return local
        # Si el proveedor lanza, la excepción sube: quien llama la trata como rechazo.
        return await self._moderador.moderar(texto)

    @property
    def proveedor(self) -> str:
        return self._moderador.proveedor

    @property
    def timeout_s(self) -> float | None:
        return self._moderador.timeout_s
