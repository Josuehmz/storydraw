"""Cuentos de invitado (modo SOLO para pruebas locales).

El invitado no tiene cuenta ni biblioteca en el servidor: su cuento vive aquí, en
memoria del proceso, hasta que la app lo recoge (o pasa la retención), y entonces se
olvida. Nada de esto toca la base de datos.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.dominio.orquestador import ResultadoCuento


@dataclass
class TrabajoInvitado:
    id: uuid.UUID
    invitado: str
    resultado: ResultadoCuento | None = None
    # Páginas compuestas, en memoria, por número de página
    imagenes: dict[int, bytes] = field(default_factory=dict)
    creado: float = field(default_factory=time.monotonic)

    @property
    def terminado(self) -> bool:
        return self.resultado is not None


class TrabajosInvitado:
    def __init__(self, retencion_s: float = 30 * 60):
        self._retencion_s = retencion_s
        self._trabajos: dict[uuid.UUID, TrabajoInvitado] = {}

    def _purgar(self) -> None:
        limite = time.monotonic() - self._retencion_s
        for clave in [k for k, t in self._trabajos.items() if t.creado < limite]:
            del self._trabajos[clave]

    def crear(self, invitado: str) -> TrabajoInvitado:
        self._purgar()
        trabajo = TrabajoInvitado(uuid.uuid4(), invitado)
        self._trabajos[trabajo.id] = trabajo
        return trabajo

    def de(self, invitado: str, trabajo_id: uuid.UUID) -> TrabajoInvitado | None:
        """Solo el invitado que lo pidió lo ve."""
        self._purgar()
        trabajo = self._trabajos.get(trabajo_id)
        return trabajo if trabajo is not None and trabajo.invitado == invitado else None

    def terminar(self, trabajo_id: uuid.UUID, resultado: ResultadoCuento, imagenes) -> None:
        trabajo = self._trabajos.get(trabajo_id)
        if trabajo is not None:
            trabajo.resultado = resultado
            trabajo.imagenes = dict(imagenes)

    def olvidar(self, trabajo_id: uuid.UUID) -> None:
        self._trabajos.pop(trabajo_id, None)

    def __len__(self) -> int:
        return len(self._trabajos)
