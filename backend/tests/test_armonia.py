"""Armonía dibujo/fondo: paleta del dibujo, contraste medido, corrección e integración.

Caso guía (pedido de Josue del 2026-11-09): un dibujo amarillo sobre un fondo amarillo «ni se
ve». Todo se prueba con Pillow, sin red.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw, ImageStat

from app.dominio.armonia import (
    CONTRASTE_MINIMO,
    Colocacion,
    analizar,
    armonizar_fondo,
    contraste,
    guia_de_color,
)
from app.dominio.composicion import Compositor, RecortadorUmbral
from app.infra.adaptadores.falsos import ImagenFalsa

AMARILLO = (250, 215, 40)
NEGRO = (30, 30, 40)


def _dibujo(color, fondo=(255, 255, 255)) -> bytes:
    """Un personaje relleno de un color con un contorno algo más oscuro, sobre blanco."""
    img = Image.new("RGB", (400, 400), fondo)
    d = ImageDraw.Draw(img)
    d.ellipse((60, 60, 340, 380), fill=color)
    borde = tuple(max(0, c - 30) for c in color)
    d.ellipse((60, 60, 340, 380), outline=borde, width=10)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()


def _png(color, tam=(1024, 1024)) -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", tam, color).save(salida, format="PNG")
    return salida.getvalue()


def _recorte(color) -> bytes:
    return RecortadorUmbral().recortar(_dibujo(color))


def _abrir(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGBA")


# ------------------------------------------------------------------ paleta


def test_un_dibujo_amarillo_se_lee_como_amarillo_y_claro():
    paleta = analizar(_abrir(_recorte(AMARILLO)))
    assert paleta.familia == "amarillo"
    assert paleta.claro and not paleta.oscuro


def test_un_dibujo_negro_se_lee_como_gris_y_oscuro():
    paleta = analizar(_abrir(_recorte(NEGRO)))
    assert paleta.familia == "gris" and paleta.tono is None
    assert paleta.oscuro


def test_el_contorno_negro_no_vuelve_negro_a_un_dibujo_de_color():
    img = Image.new("RGB", (400, 400), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((60, 60, 340, 380), fill=AMARILLO, outline=(20, 20, 20), width=25)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    paleta = analizar(_abrir(RecortadorUmbral().recortar(salida.getvalue())))
    assert paleta.familia == "amarillo"


def test_la_guia_pide_colores_que_contrastan_y_suelo_despejado():
    guia = guia_de_color(analizar(_abrir(_recorte(AMARILLO))))
    assert "blue" in guia and "lilac" in guia
    assert "yellow" not in guia  # sin negativos: flux pintaría justo ese color
    assert "rich, saturated" in guia  # dibujo claro: fondo con algo de profundidad
    assert "not " not in guia  # todo en positivo: «not pale» le pedía a flux lo pálido
    assert "empty patch of ground in the lower center" in guia
    assert "character" not in guia  # flux lo pintaría
    reforzada = guia_de_color(analizar(_abrir(_recorte(AMARILLO))), reforzada=True)
    assert "painted almost entirely in soft sky blue" in reforzada and "yellow" not in reforzada


def test_la_guia_de_un_dibujo_oscuro_pide_tonos_claros():
    guia = guia_de_color(analizar(_abrir(_recorte(NEGRO))))
    assert "light, airy pastel" in guia
    assert "palette:" not in guia  # sin color dominante no hay complementario que pedir


# ------------------------------------------------------------------ contraste


def _colocado(color) -> tuple[Image.Image, Colocacion]:
    dibujo = _abrir(_recorte(color)).resize((400, 400))
    return dibujo, Colocacion(300, 560, 400, 400)


def test_amarillo_sobre_amarillo_queda_bajo_el_umbral_y_sobre_azul_no():
    dibujo, donde = _colocado(AMARILLO)
    amarillo = Image.new("RGB", (1024, 1024), (245, 210, 70))
    azul = Image.new("RGB", (1024, 1024), (110, 160, 210))
    assert contraste(amarillo, dibujo, donde) < 15
    assert contraste(azul, dibujo, donde) > 40


def test_armonizar_sube_el_contraste_solo_alrededor_del_dibujo():
    dibujo, donde = _colocado(AMARILLO)
    fondo = Image.new("RGB", (1024, 1024), (245, 210, 70))
    corregido, inicial, final = armonizar_fondo(fondo, dibujo, donde, analizar(dibujo))
    assert inicial < 15
    assert final >= CONTRASTE_MINIMO
    assert contraste(corregido, dibujo, donde) == final

    # Lejos del dibujo cambia menos (toma la misma luz, sin mancha) que junto a él
    def cambio(xy):
        return sum(
            abs(a - b) for a, b in zip(corregido.getpixel(xy), fondo.getpixel(xy), strict=True)
        )

    assert 0 < cambio((10, 10)) < cambio((donde.x - 5, donde.y + 200))


def test_si_ya_contrasta_no_se_toca_el_fondo():
    dibujo, donde = _colocado(AMARILLO)
    fondo = Image.new("RGB", (1024, 1024), (110, 160, 210))
    corregido, inicial, final = armonizar_fondo(fondo, dibujo, donde, analizar(dibujo))
    assert corregido is fondo and inicial == final


# ------------------------------------------------------------------ composición


def test_componer_un_dibujo_amarillo_sobre_fondo_amarillo_lo_hace_visible():
    compositor = Compositor(RecortadorUmbral())
    fondo = _png((245, 210, 70))
    recorte = _recorte(AMARILLO)
    assert compositor.contraste(fondo, recorte, 2) < CONTRASTE_MINIMO
    png, armonia = compositor.componer_armonico(fondo, recorte, 2)
    assert armonia.contraste_inicial < CONTRASTE_MINIMO <= armonia.contraste_final
    assert armonia.corregido
    pagina = _abrir(png)
    assert pagina.size == (1024, 1024)
    # El dibujo sigue siendo amarillo: el ajuste de luz es leve
    amarillos = sum(1 for r, g, b, _ in pagina.getdata() if r > 200 and g > 160 and b < 110)
    assert amarillos > 20_000


def test_el_dibujo_proyecta_una_sombra_de_contacto_y_todo_lleva_textura():
    compositor = Compositor(RecortadorUmbral())
    gris = (180, 180, 180)
    png, _ = compositor.componer_armonico(_png(gris), _recorte((70, 170, 60)), 2)
    pagina = _abrir(png).convert("RGB")
    # Página 2: dibujo centrado, apoyado a ~7 % del borde inferior
    pie = 1024 - int(1024 * 0.07)
    bajo_el_dibujo = ImageStat.Stat(pagina.crop((480, pie - 4, 544, pie + 4))).mean
    lejos = ImageStat.Stat(pagina.crop((10, pie - 4, 74, pie + 4))).mean
    assert sum(bajo_el_dibujo) < sum(lejos) - 30  # más oscuro justo bajo la base
    # La textura de lápiz cubre también el fondo liso: ya no es un color plano
    assert ImageStat.Stat(pagina.crop((10, 10, 200, 200))).stddev[0] > 1.0


# ------------------------------------------------------------------ orquestador


class ImagenDeColor(ImagenFalsa):
    """Fondos lisos: el primer color y, si se pide otra vez (reforzado), el último."""

    def __init__(self, colores):
        super().__init__()
        self.colores = list(colores)
        self.descripciones: list[str] = []

    async def generar_fondo(self, descripcion):
        from app.dominio.puertos import ResultadoImagen, Uso

        self.llamadas += 1
        self.descripciones.append(descripcion)
        color = self.colores[-1] if "almost entirely" in descripcion else self.colores[0]
        return ResultadoImagen(_png(color), Uso(imagenes=1))


def _crear_cuento_con_dibujo(entorno, dibujo: bytes) -> str:
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    r = entorno.cliente.post(
        "/v1/cuentos",
        data={"perfil_id": perfil, "personaje": "un pollito"},
        files={"dibujo": ("dibujo.png", dibujo, "image/png")},
        headers=cab,
    )
    assert r.status_code in (200, 201, 202), r.text
    cuento = entorno.cliente.get(f"/v1/cuentos/{r.json()['id']}", headers=cab).json()
    assert cuento["estado"] == "listo"
    return r.json()["id"]


def test_el_fondo_se_pide_con_la_paleta_del_dibujo(crear_entorno, caplog):
    entorno = crear_entorno()
    imagen = ImagenDeColor([(110, 160, 210)])  # azul: contrasta a la primera
    entorno.c.orquestador.imagen = imagen
    with caplog.at_level("INFO"):
        _crear_cuento_con_dibujo(entorno, _dibujo(AMARILLO))
    assert imagen.llamadas == 3  # sin reintentos: ya contrastaba
    # Las escenas del cuento falso son «meadow», «river» (de día) y «sunset» (atardecer): la
    # paleta que contrasta va dentro del ambiente de cada una.
    dia, _, atardecer = imagen.descripciones
    assert "Background color palette: soft sky blue" in dia
    assert "Background color palette: dusky violet" in atardecer
    assert all("empty patch of ground" in d for d in imagen.descripciones)
    assert all("character" not in d for d in imagen.descripciones)
    assert "paleta_dibujo=amarillo" in caplog.text
    assert "contraste_final=" in caplog.text


def test_un_fondo_sin_contraste_se_pide_otra_vez_una_sola_vez(crear_entorno, caplog):
    entorno = crear_entorno(regenerar_fondo_sin_contraste=True)
    imagen = ImagenDeColor([(245, 210, 70), (110, 160, 210)])  # amarillo y luego azul
    entorno.c.orquestador.imagen = imagen
    with caplog.at_level("INFO"):
        _crear_cuento_con_dibujo(entorno, _dibujo(AMARILLO))
    assert imagen.llamadas == 6  # 3 páginas x (fondo + otro reforzado)
    reforzadas = [d for d in imagen.descripciones if "painted almost entirely in" in d]
    assert len(reforzadas) == 3
    assert "otra_vez=" in caplog.text


def test_si_el_segundo_tampoco_contrasta_lo_corrige_la_composicion(crear_entorno, caplog):
    entorno = crear_entorno(regenerar_fondo_sin_contraste=True)
    imagen = ImagenDeColor([(245, 210, 70)])  # siempre amarillo
    entorno.c.orquestador.imagen = imagen
    with caplog.at_level("INFO"):
        _crear_cuento_con_dibujo(entorno, _dibujo(AMARILLO))
    assert imagen.llamadas == 6  # nunca más de un intento extra por página
    finales = [
        float(linea.split("contraste_final=")[1].split()[0])
        for linea in caplog.text.splitlines()
        if "contraste_final=" in linea
    ]
    assert len(finales) == 3 and all(c >= CONTRASTE_MINIMO for c in finales)


def test_por_defecto_no_se_pide_otro_fondo_y_la_composicion_corrige(crear_entorno, caplog):
    entorno = crear_entorno()
    assert entorno.c.settings.regenerar_fondo_sin_contraste is False
    imagen = ImagenDeColor([(245, 210, 70)])
    entorno.c.orquestador.imagen = imagen
    with caplog.at_level("INFO"):
        _crear_cuento_con_dibujo(entorno, _dibujo(AMARILLO))
    assert imagen.llamadas == 3  # ni tiempo ni neuronas de más
    assert caplog.text.count("contraste_final=") == 3


@pytest.mark.parametrize("valor", [-1, 101])
def test_el_umbral_de_contraste_se_valida(tmp_path, valor):
    from pydantic import ValidationError

    from tests.conftest import settings_de_prueba

    with pytest.raises(ValidationError):
        settings_de_prueba(tmp_path / "bd.db", contraste_minimo_fondo=valor)
