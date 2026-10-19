"""Costo por cuento: cada llamada reporta su uso y aquí se convierte a USD."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.dominio.puertos import Uso

Capacidad = Literal["vision", "texto", "moderacion", "imagen", "voz"]


@dataclass(frozen=True)
class Tarifario:
    texto_entrada_mtok: float = 0.20
    texto_salida_mtok: float = 1.20
    vision_entrada_mtok: float = 0.20
    vision_salida_mtok: float = 1.20
    imagen: float = 0.005
    voz_mil_caracteres: float = 0.05

    def costo(self, capacidad: Capacidad, uso: Uso) -> float:
        if capacidad == "vision":
            return (
                uso.tokens_entrada * self.vision_entrada_mtok
                + uso.tokens_salida * self.vision_salida_mtok
            ) / 1_000_000
        if capacidad == "texto":
            return (
                uso.tokens_entrada * self.texto_entrada_mtok
                + uso.tokens_salida * self.texto_salida_mtok
            ) / 1_000_000
        if capacidad == "imagen":
            return uso.imagenes * self.imagen
        if capacidad == "voz":
            return uso.caracteres / 1000 * self.voz_mil_caracteres
        return 0.0  # el endpoint de moderación de OpenAI no se factura
