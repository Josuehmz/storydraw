"""Costo por cuento: cada llamada reporta su uso y aquí se convierte a USD."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.dominio.puertos import Uso

Capacidad = Literal["vision", "texto", "moderacion", "imagen"]


@dataclass(frozen=True)
class Tarifario:
    texto_entrada_mtok: float = 0.20
    texto_salida_mtok: float = 1.20
    vision_entrada_mtok: float = 0.20
    vision_salida_mtok: float = 1.20
    imagen: float = 0.005

    def costo(self, capacidad: Capacidad, uso: Uso) -> float:
        if uso.costo_usd is not None:
            return uso.costo_usd  # el adaptador ya lo calculó con su propia tarifa
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
        return 0.0  # el endpoint de moderación de OpenAI no se factura
