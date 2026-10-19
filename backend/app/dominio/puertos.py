"""Puertos del dominio: un contrato por capacidad, nunca por proveedor.

El orquestador depende solo de estas interfaces (zócalos del diagrama de componentes);
cada adaptador de `app/infra/adaptadores` provee la suya (bola). Cambiar de proveedor
es escribir otra clase que cumpla el contrato y apuntar la variable de entorno a ella.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Uso:
    """Lo facturable de una llamada: alimenta el costo por cuento."""

    tokens_entrada: int = 0
    tokens_salida: int = 0
    imagenes: int = 0
    caracteres: int = 0
    # Workers AI factura en neuronas; se guardan para auditar el costo.
    neuronas: float = 0.0
    # Si el adaptador ya calculó su costo (Ollama = 0, Cloudflare = neuronas a USD),
    # el tarifario lo respeta en vez de aplicar las tarifas por token.
    costo_usd: float | None = None


@dataclass(frozen=True)
class Hipotesis:
    etiqueta: str
    confianza: float


@dataclass(frozen=True)
class ResultadoVision:
    hipotesis: list[Hipotesis]
    uso: Uso = field(default_factory=Uso)


@dataclass(frozen=True)
class SolicitudCuento:
    """Lo único que sale hacia el modelo: ni el nombre ni la imagen del niño."""

    personaje: str
    edad: int
    paginas: int = 3


@dataclass(frozen=True)
class PaginaTexto:
    texto: str
    escena: str


@dataclass(frozen=True)
class CuentoTexto:
    titulo: str
    paginas: list[PaginaTexto]
    uso: Uso = field(default_factory=Uso)


@dataclass(frozen=True)
class VeredictoModeracion:
    aprobado: bool
    categorias: list[str] = field(default_factory=list)
    uso: Uso = field(default_factory=Uso)


@dataclass(frozen=True)
class ResultadoImagen:
    png: bytes
    uso: Uso = field(default_factory=Uso)


@dataclass(frozen=True)
class ResultadoAudio:
    mp3: bytes
    uso: Uso = field(default_factory=Uso)


class IVision(ABC):
    proveedor: str = "desconocido"
    # Timeout propio del adaptador (p. ej. Ollama por CPU tarda minutos). None = el global.
    timeout_s: float | None = None

    @abstractmethod
    async def identificar(self, imagen_png: bytes) -> ResultadoVision:
        """Devuelve de 1 a 4 hipótesis de qué dibujó el niño, con su confianza (0 a 1)."""


class ITexto(ABC):
    proveedor: str = "desconocido"
    timeout_s: float | None = None

    @abstractmethod
    async def escribir_cuento(self, solicitud: SolicitudCuento) -> CuentoTexto:
        """Escribe un cuento de `solicitud.paginas` páginas con una escena por página."""


class IModerador(ABC):
    """Proveedor de moderación. Se elige aparte del de texto (`PROVEEDOR_MODERACION`)."""

    proveedor: str = "desconocido"
    timeout_s: float | None = None

    @abstractmethod
    async def moderar(self, texto: str) -> VeredictoModeracion:
        """Clasifica un texto. Si el proveedor falla, debe lanzar: nunca aprobar por defecto."""


class IImagen(ABC):
    proveedor: str = "desconocido"
    timeout_s: float | None = None

    @abstractmethod
    async def generar_fondo(self, descripcion: str) -> ResultadoImagen:
        """Genera un fondo sin personajes (PNG) para una página."""


class IVoz(ABC):
    proveedor: str = "desconocido"
    timeout_s: float | None = None

    @abstractmethod
    async def narrar(self, texto: str) -> ResultadoAudio:
        """Sintetiza la narración de una página (MP3)."""


class ICorreo(ABC):
    proveedor: str = "desconocido"

    @abstractmethod
    async def enviar(self, para: str, asunto: str, cuerpo: str) -> None:
        """Envía un correo transaccional de texto plano."""


class IAlmacen(ABC):
    @abstractmethod
    async def guardar(self, clave: str, datos: bytes, tipo: str) -> None: ...

    @abstractmethod
    async def leer(self, clave: str) -> bytes: ...

    @abstractmethod
    async def borrar_prefijo(self, prefijo: str) -> int: ...


class IRecortador(ABC):
    @abstractmethod
    def recortar(self, png_blanco: bytes) -> bytes:
        """Recibe el dibujo con fondo blanco y devuelve un PNG RGBA con fondo transparente."""
