"""Adaptadores falsos: deterministas, sin red y sin claves.

Sirven para las pruebas y para correr todo en local con `PROVEEDOR_*=falso`. En producción
la configuración los rechaza. Cada uno tiene `fallar` para simular la caída del proveedor.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from app.dominio.puertos import (
    AtributosDibujo,
    CuentoTexto,
    Hipotesis,
    ICorreo,
    IImagen,
    IModerador,
    ITexto,
    IVision,
    IVoz,
    PaginaTexto,
    ResultadoAudio,
    ResultadoImagen,
    ResultadoVision,
    SolicitudCuento,
    Uso,
    VeredictoModeracion,
)


class ProveedorCaido(RuntimeError):
    pass


class VisionFalsa(IVision):
    proveedor = "falso"

    def __init__(self) -> None:
        self.fallar = False
        self.llamadas = 0
        self.hipotesis = [
            Hipotesis("un dragón", 0.81),
            Hipotesis("un dinosaurio", 0.44),
            Hipotesis("un gato", 0.12),
        ]
        self.atributos = AtributosDibujo(("verde",), ("cola larga", "alas"), "alegre")

    async def identificar(self, imagen_png: bytes) -> ResultadoVision:
        self.llamadas += 1
        if self.fallar:
            raise ProveedorCaido("visión caída")
        return ResultadoVision(
            list(self.hipotesis), Uso(tokens_entrada=2048, tokens_salida=60), self.atributos
        )


class TextoFalso(ITexto, IModerador):
    """Escribe un cuento de plantilla. `cuentos_forzados` permite inyectar respuestas."""

    proveedor = "falso"

    def __init__(self) -> None:
        self.fallar = False
        self.fallar_moderacion = False
        self.fallos_pendientes = 0
        self.cuentos_forzados: list[CuentoTexto] = []
        self.palabras_marcadas = ("violencia", "monstruo malvado")
        self.llamadas_cuento = 0
        self.llamadas_moderacion = 0
        self.solicitudes: list[SolicitudCuento] = []
        self.textos_moderados: list[str] = []

    async def escribir_cuento(self, solicitud: SolicitudCuento) -> CuentoTexto:
        self.llamadas_cuento += 1
        self.solicitudes.append(solicitud)
        if self.fallar:
            raise ProveedorCaido("texto caído")
        if self.fallos_pendientes > 0:
            self.fallos_pendientes -= 1
            raise ProveedorCaido("fallo transitorio")
        if self.cuentos_forzados:
            return self.cuentos_forzados.pop(0)
        p = solicitud.nombre or solicitud.personaje
        paginas = [
            PaginaTexto(f"Había una vez {p} que soñaba con volar entre las nubes.", "meadow"),
            PaginaTexto(f"Un día, {p} encontró un mapa brillante junto al río.", "river"),
            PaginaTexto(f"Al final, {p} compartió su tesoro con todos sus amigos.", "sunset"),
        ]
        return CuentoTexto(f"La aventura de {p}", paginas, Uso(800, 700))

    async def moderar(self, texto: str) -> VeredictoModeracion:
        self.llamadas_moderacion += 1
        self.textos_moderados.append(texto)
        if self.fallar_moderacion:
            raise ProveedorCaido("moderación caída")
        bajo = texto.lower()
        marcadas = [p for p in self.palabras_marcadas if p in bajo]
        return VeredictoModeracion(not marcadas, ["violence"] if marcadas else [], Uso())


class ImagenFalsa(IImagen):
    proveedor = "falso"

    def __init__(self) -> None:
        self.fallar = False
        self.llamadas = 0

    async def generar_fondo(self, descripcion: str) -> ResultadoImagen:
        self.llamadas += 1
        if self.fallar:
            raise ProveedorCaido("imagen caída")
        img = Image.new("RGB", (1024, 1024), (170, 220, 250))
        ImageDraw.Draw(img).rectangle([0, 760, 1024, 1024], fill=(120, 200, 110))
        salida = io.BytesIO()
        img.save(salida, format="PNG")
        return ResultadoImagen(salida.getvalue(), Uso(imagenes=1))


class ImagenNoDisponible(IImagen):
    """`PROVEEDOR_IMAGEN=ninguno`: el proveedor no genera imágenes (p. ej. Ollama).

    El orquestador no la llama (`disponible = False`) y usa un fondo del banco. Si alguien
    la llama igual, falla al instante.
    """

    proveedor = "ninguno"
    disponible = False

    async def generar_fondo(self, descripcion: str) -> ResultadoImagen:
        raise ProveedorCaido("sin proveedor de imagen configurado")


class CorreoFalso(ICorreo):
    proveedor = "falso"

    def __init__(self) -> None:
        self.enviados: list[tuple[str, str, str]] = []

    async def enviar(self, para: str, asunto: str, cuerpo: str) -> None:
        self.enviados.append((para, asunto, cuerpo))


class VozNoDisponible(IVoz):
    """`PROVEEDOR_VOZ=ninguno`: el cuento se entrega escrito, con el aviso de sin narración."""

    proveedor = "ninguno"
    disponible = False

    async def narrar(self, texto: str) -> ResultadoAudio:
        raise ProveedorCaido("sin proveedor de voz configurado")


class VozFalsa(IVoz):
    proveedor = "falso"

    def __init__(self) -> None:
        self.fallar = False
        self.llamadas = 0

    async def narrar(self, texto: str) -> ResultadoAudio:
        self.llamadas += 1
        if self.fallar:
            raise ProveedorCaido("voz caída")
        # Cabecera ID3 mínima: suficiente para probar el flujo, no es audio real.
        return ResultadoAudio(
            b"ID3\x04\x00\x00\x00\x00\x00\x00" + texto.encode()[:64], Uso(caracteres=len(texto))
        )
