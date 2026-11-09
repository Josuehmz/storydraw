"""Segunda vuelta de los fondos (2026-11-09, «dale esos ajustes a fors»): ambiente primero,
color del lugar en la escena y sin sombra para lo que vuela o nada. Todo local, sin red."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw, ImageStat

from app.dominio.armonia import analizar, delta_e, guia_de_color, lab
from app.dominio.composicion import Compositor, RecortadorUmbral
from app.dominio.escena import ambiente_de, en_el_aire, recolorear_escena, recolorear_texto
from app.dominio.puertos import CuentoTexto, PaginaTexto, ResultadoImagen, Uso
from app.infra.adaptadores.falsos import ImagenFalsa

AMARILLO = (250, 215, 40)
NEGRO = (30, 30, 40)


def _recorte(color) -> bytes:
    img = Image.new("RGB", (400, 400), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((60, 60, 340, 380), fill=color)
    d.ellipse((60, 60, 340, 380), outline=tuple(max(0, c - 30) for c in color), width=10)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return RecortadorUmbral().recortar(salida.getvalue())


def _png(color) -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (1024, 1024), color).save(salida, format="PNG")
    return salida.getvalue()


def _abrir(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as img:
        return img.convert("RGB")


# ------------------------------------------------------------------ ambiente


@pytest.mark.parametrize(
    ("escena", "ambiente"),
    [
        ("a quiet village street at night with dark houses and glowing windows", "noche"),
        ("a starry sky over the hills", "noche"),
        ("a farm at sunset with orange clouds", "atardecer"),
        ("a coral reef under the sea", "bajo_agua"),
        ("an underwater cave at night", "bajo_agua"),  # el agua manda sobre la hora
        ("a cozy bedroom with a lamp", "interior"),
        ("a sunny farm with a red barn", "dia"),
        ("a meadow", "dia"),
    ],
)
def test_el_ambiente_se_lee_de_la_escena(escena, ambiente):
    assert ambiente_de(escena) == ambiente


def test_si_la_escena_no_dice_la_hora_se_mira_el_texto():
    assert ambiente_de("a quiet street", "Esa noche, la luna brillaba.") == "noche"


# ------------------------------------------------------------------ vuela o nada


@pytest.mark.parametrize(
    ("personaje", "ambiente", "aire"),
    [
        ("un pájaro azul", "dia", True),
        ("Una mariposa", "dia", True),
        ("un avión", "dia", True),
        ("una nube", "dia", True),
        ("un globo", "dia", True),
        ("un pez", "bajo_agua", True),
        ("un dragón", "bajo_agua", True),  # bajo el agua, todo nada
        ("un cangrejo", "bajo_agua", False),  # salvo lo que camina por el fondo
        ("un pollito", "dia", False),
        ("un gato", "noche", False),
        ("un soldado", "dia", False),  # «sol» solo como palabra entera
        ("una estrella de mar", "dia", False),
    ],
)
def test_lo_que_vuela_o_nada_se_reconoce_por_el_personaje(personaje, ambiente, aire):
    assert en_el_aire(personaje, ambiente) is aire


# ------------------------------------------------------------------ color del lugar


def test_el_trigal_dorado_de_un_pollito_amarillo_pasa_a_verde():
    escena, cambios = recolorear_escena(
        "a sunny farm with a golden wheat field and a red barn under a clear sky", "amarillo"
    )
    assert "golden" not in escena and "fresh green wheat field" in escena
    assert "red barn" in escena  # el rojo no choca con el amarillo
    assert cambios == [("golden", "fresh green")]


def test_cada_cosa_toma_un_color_que_le_queda():
    escena, _ = recolorear_escena(
        "light yellow sand dunes under a yellow sky with a yellow sun", "amarillo"
    )
    assert "pale silver-grey sand" in escena  # la arena no se vuelve verde
    assert "soft blue sky" in escena
    assert "yellow sun" in escena  # una fuente de luz pequeña se respeta


def test_dos_colores_de_la_misma_familia_toman_dos_reemplazos():
    escena, cambios = recolorear_escena("a coral reef with red and orange corals", "rojo")
    assert escena == "a coral reef with teal and aqua corals"
    assert len(cambios) == 2


def test_un_cielo_azul_de_dia_se_aclara_sin_volverse_atardecer():
    escena, _ = recolorear_escena("a clear blue sky above green hills", "azul")
    assert "pale misty sky" in escena and "green hills" in escena


def test_sin_choque_o_con_dibujo_gris_la_escena_no_cambia():
    escena = "a golden wheat field under a blue sky"
    assert recolorear_escena(escena, "rojo") == (escena, [])
    assert recolorear_escena(escena, "gris") == (escena, [])


def test_el_texto_solo_cambia_el_color_del_lugar_con_genero_y_numero():
    texto, cambios = recolorear_texto(
        "Pipo corrió por el trigal dorado y las colinas amarillas. El pollito amarillo rió.",
        "amarillo",
    )
    assert texto == (
        "Pipo corrió por el trigal verde y las colinas verdes. El pollito amarillo rió."
    )
    assert cambios == [("dorado", "verde"), ("amarillas", "verdes")]
    texto, _ = recolorear_texto("Rex vivía en un valle verde junto a la selva verde.", "verde")
    assert texto == "Rex vivía en un valle dorado junto a la selva dorada."


def test_el_texto_sin_color_del_lugar_queda_igual():
    texto = "El pollito amarillo encontró un amigo en la granja."
    assert recolorear_texto(texto, "amarillo") == (texto, [])
    # Si no hay un cambio natural (arena roja para un pez rojo), el texto queda igual.
    assert recolorear_texto("La arena roja brillaba.", "rojo")[1] == []


# ------------------------------------------------------------------ paleta en el ambiente


def test_de_noche_un_dibujo_oscuro_pide_luz_de_farol_no_un_dia():
    guia = guia_de_color(analizar(_abrir_rgba(_recorte(NEGRO))), ambiente="noche")
    assert "night scene" in guia and "dark sky" in guia and "lamplight" in guia
    assert "pastel" not in guia and "airy" not in guia


def test_de_noche_un_dibujo_amarillo_contrasta_con_azules_profundos():
    guia = guia_de_color(analizar(_abrir_rgba(_recorte(AMARILLO))), ambiente="noche")
    assert "midnight blue" in guia and "night scene" in guia
    assert "yellow" not in guia


def test_lo_que_vuela_pide_cielo_abierto_y_lo_que_nada_agua_abierta():
    paleta = analizar(_abrir_rgba(_recorte(AMARILLO)))
    cielo = guia_de_color(paleta, aire=True)
    agua = guia_de_color(paleta, ambiente="bajo_agua", aire=True)
    assert "open sky in the center" in cielo and "patch of ground" not in cielo
    assert "open water in the center" in agua


def _abrir_rgba(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as img:
        return img.convert("RGBA")


# ------------------------------------------------------------------ composición


def _l(img: Image.Image, caja) -> float:
    return lab(tuple(int(v) for v in ImageStat.Stat(img.crop(caja)).mean))[0]


def test_la_noche_sigue_siendo_noche_y_el_dibujo_oscuro_lleva_un_halo():
    compositor = Compositor(RecortadorUmbral())
    noche = (25, 30, 70)
    png, armonia = compositor.componer_armonico(_png(noche), _recorte(NEGRO), 2, "noche")
    pagina = _abrir(png)
    # Lejos del dibujo (esquinas de arriba) la escena conserva su oscuridad.
    for caja in ((10, 10, 150, 150), (874, 10, 1014, 150)):
        assert abs(_l(pagina, caja) - lab(noche)[0]) < 4
    # Junto al dibujo hay luz (el halo del farol): más clara que el cielo.
    junto = _l(pagina, (250, 700, 320, 760))
    assert junto > lab(noche)[0] + 8
    assert armonia.contraste_final >= armonia.contraste_inicial


def test_de_dia_la_correccion_si_llega_un_poco_a_todo_el_fondo():
    """Contraste con la noche: de día una parte de la luz baña todo el paisaje (sin mancha)."""
    compositor = Compositor(RecortadorUmbral())
    amarillo = (245, 210, 70)
    png, armonia = compositor.componer_armonico(_png(amarillo), _recorte(AMARILLO), 2, "dia")
    assert armonia.corregido
    esquina = ImageStat.Stat(_abrir(png).crop((10, 10, 150, 150))).mean
    assert delta_e(lab(tuple(int(v) for v in esquina)), lab(amarillo)) > 3


def test_una_noche_amarilla_se_corrige_sin_volverla_de_dia():
    compositor = Compositor(RecortadorUmbral())
    farol = (200, 170, 60)  # calle de noche bañada en luz amarilla, con un pollito amarillo
    png, _ = compositor.componer_armonico(_png(farol), _recorte(AMARILLO), 2, "noche")
    pagina = _abrir(png)
    assert abs(_l(pagina, (10, 10, 150, 150)) - lab(farol)[0]) < 4


def test_lo_que_vuela_no_lleva_sombra_de_contacto_y_va_mas_arriba():
    compositor = Compositor(RecortadorUmbral())
    gris = (180, 180, 180)
    verde = (70, 170, 60)
    pie = 1024 - int(1024 * 0.07)
    caja = (480, pie - 4, 544, pie + 4)
    en_suelo = _abrir(compositor.componer(_png(gris), _recorte(verde), 2))
    volando = _abrir(compositor.componer(_png(gris), _recorte(verde), 2, aire=True))
    lejos = sum(ImageStat.Stat(volando.crop((10, pie - 4, 74, pie + 4))).mean)
    assert sum(ImageStat.Stat(en_suelo.crop(caja)).mean) < lejos - 30  # con sombra
    assert abs(sum(ImageStat.Stat(volando.crop(caja)).mean) - lejos) < 12  # sin sombra
    # Volando, el dibujo no está apoyado abajo: la franja del suelo queda libre.
    assert sum(ImageStat.Stat(volando.crop((400, pie - 40, 624, pie - 20))).mean) > lejos - 12


# ------------------------------------------------------------------ pipeline


class ImagenQueAnota(ImagenFalsa):
    def __init__(self, color=(110, 160, 210)):
        super().__init__()
        self.color = color
        self.descripciones: list[str] = []

    async def generar_fondo(self, descripcion):
        self.llamadas += 1
        self.descripciones.append(descripcion)
        return ResultadoImagen(_png(self.color), Uso(imagenes=1))


def _dibujo_png(color) -> bytes:
    img = Image.new("RGB", (400, 400), (255, 255, 255))
    ImageDraw.Draw(img).ellipse((60, 60, 340, 380), fill=color)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()


def test_el_cuento_cambia_el_color_del_lugar_y_respeta_la_noche(crear_entorno, caplog):
    entorno = crear_entorno()
    imagen = ImagenQueAnota()
    entorno.c.orquestador.imagen = imagen
    entorno.c.texto.cuentos_forzados = [
        CuentoTexto(
            "Pipo y el trigal",
            [
                PaginaTexto(
                    "Pipo saltaba por el trigal dorado.",
                    "a sunny farm with a golden wheat field and a red barn",
                ),
                PaginaTexto("Pipo vio un río.", "a river crossing a yellow meadow on a sunny day"),
                PaginaTexto(
                    "Esa noche, Pipo durmió feliz.",
                    "the farm at night under the moon with dark hills",
                ),
            ],
            Uso(10, 10),
        )
    ]
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    with caplog.at_level("INFO"):
        r = entorno.cliente.post(
            "/v1/cuentos",
            data={"perfil_id": perfil, "personaje": "un pollito"},
            files={"dibujo": ("dibujo.png", _dibujo_png(AMARILLO), "image/png")},
            headers=cab,
        )
    cuento = entorno.cliente.get(f"/v1/cuentos/{r.json()['id']}", headers=cab).json()
    assert cuento["estado"] == "listo"
    primera, segunda, tercera = imagen.descripciones
    assert "golden" not in primera and "fresh green wheat field" in primera
    assert "yellow" not in segunda and "fresh green meadow" in segunda
    assert "night scene" in tercera and "midnight blue" in tercera
    # El niño lee lo mismo que ve: el trigal ahora es verde; lo demás queda igual.
    textos = [p["texto"] for p in cuento["paginas"]]
    assert textos[0] == "Pipo saltaba por el trigal verde."
    assert textos[2] == "Esa noche, Pipo durmió feliz."
    assert "ambiente=noche" in caplog.text and "color_escena=golden>fresh green" in caplog.text
