"""Pipeline completo con adaptadores falsos, reintento por paso y degradación."""

from __future__ import annotations

import io

from PIL import Image

from tests.conftest import dibujo_png


def _cuento(entorno, cabeceras, cuento_id):
    r = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cabeceras)
    assert r.status_code == 200, r.text
    return r.json()


def _pasos(entorno, admin, cuento_id):
    metricas = entorno.cliente.get("/v1/operacion/cuentos", headers=admin).json()
    fila = next(m for m in metricas if m["id"] == cuento_id)
    return {p["paso"]: p for p in fila["pasos"]}, fila


def test_identificacion_asistida(entorno):
    cab = entorno.registrar("a@correo.com")
    r = entorno.cliente.post(
        "/v1/dibujos/identificar",
        files={"dibujo": ("d.png", dibujo_png(), "image/png")},
        headers=cab,
    )
    assert r.status_code == 200
    datos = r.json()
    assert datos["disponible"] is True
    confianzas = [h["confianza"] for h in datos["hipotesis"]]
    assert confianzas == sorted(confianzas, reverse=True)
    assert datos["hipotesis"][0]["etiqueta"] == "un dragón"


def test_identificacion_degrada_si_cae_la_vision(entorno):
    cab = entorno.registrar("a@correo.com")
    entorno.c.vision.fallar = True
    r = entorno.cliente.post(
        "/v1/dibujos/identificar",
        files={"dibujo": ("d.png", dibujo_png(), "image/png")},
        headers=cab,
    )
    assert r.status_code == 200
    assert r.json() == {"disponible": False, "hipotesis": []}
    assert entorno.c.vision.llamadas == 2  # 1 intento + 1 reintento


def test_dibujo_invalido(entorno):
    cab = entorno.registrar("a@correo.com")
    r = entorno.cliente.post(
        "/v1/dibujos/identificar",
        files={"dibujo": ("d.png", b"no soy una imagen", "image/png")},
        headers=cab,
    )
    assert r.status_code == 422


def test_pipeline_completo(entorno):
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)

    r = entorno.crear_cuento(cab, perfil)
    assert r.status_code == 202
    cuento_id = r.json()["id"]

    cuento = _cuento(entorno, cab, cuento_id)
    assert cuento["estado"] == "listo"
    assert cuento["titulo"] == "La aventura de un dragón"
    assert cuento["avisos"] == []
    assert [p["numero"] for p in cuento["paginas"]] == [1, 2, 3]
    assert all(p["audio_url"] for p in cuento["paginas"])

    img = entorno.cliente.get(cuento["paginas"][0]["imagen_url"], headers=cab)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(img.content)).size == (1024, 1024)
    audio = entorno.cliente.get(cuento["paginas"][0]["audio_url"], headers=cab)
    assert audio.status_code == 200 and audio.content.startswith(b"ID3")

    # El dibujo nunca se persiste: en el almacén solo hay páginas compuestas y audio.
    claves = set(entorno.c.almacen.objetos)
    assert claves == {f"cuentos/{cuento_id}/paginas/{n}.png" for n in (1, 2, 3)} | {
        f"cuentos/{cuento_id}/audio/{n}.mp3" for n in (1, 2, 3)
    }

    biblioteca = entorno.cliente.get(f"/v1/perfiles/{perfil}/cuentos", headers=cab).json()
    assert [c["id"] for c in biblioteca] == [cuento_id]

    pasos, fila = _pasos(entorno, admin, cuento_id)
    assert list(pasos) == ["identificar", "escribir", "moderar", "escenarios", "narrar"]
    # El niño ya dijo qué dibujó, pero la visión igual lee los rasgos del dibujo
    assert pasos["identificar"]["estado"] == "ok"
    assert all(pasos[p]["estado"] == "ok" for p in ("escribir", "moderar", "escenarios", "narrar"))
    assert fila["latencia_ms"] is not None
    # 800/700 tokens de texto + 3 imágenes + caracteres narrados
    assert fila["costo_usd"] > 0.015

    resumen = entorno.cliente.get("/v1/operacion/resumen", headers=admin).json()
    assert resumen["cuentos"] == 1 and resumen["por_estado"] == {"listo": 1}
    assert resumen["costo_total_usd"] == fila["costo_usd"]


def test_sin_personaje_usa_la_vision(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil, personaje=None).json()["id"]
    cuento = _cuento(entorno, cab, cuento_id)
    assert cuento["personaje"] == "un dragón"


def test_degradacion_sin_vision_y_sin_personaje(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.vision.fallar = True
    cuento = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil, personaje=None).json()["id"])
    assert cuento["estado"] == "listo"
    assert cuento["personaje"] == "un amigo mágico"
    assert "sin_identificacion" in cuento["avisos"]


def test_degradacion_sin_imagen_usa_fondo_del_banco(entorno):
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.imagen.fallar = True
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = _cuento(entorno, cab, cuento_id)
    assert cuento["estado"] == "listo"
    assert cuento["avisos"] == ["sin_escenarios"]
    assert len(cuento["paginas"]) == 3
    assert all(p["audio_url"] for p in cuento["paginas"])  # la voz no se bloquea
    img = entorno.cliente.get(cuento["paginas"][2]["imagen_url"], headers=cab)
    assert Image.open(io.BytesIO(img.content)).size == (1024, 1024)
    pasos, _ = _pasos(entorno, admin, cuento_id)
    assert pasos["escenarios"]["estado"] == "degradado"
    assert pasos["escenarios"]["intentos"] == 6  # 3 páginas × (1 intento + 1 reintento)
    assert pasos["escenarios"]["costo_usd"] == 0


def test_degradacion_sin_voz_y_reintento_solo_de_la_narracion(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.voz.fallar = True
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = _cuento(entorno, cab, cuento_id)
    assert cuento["estado"] == "listo"
    assert cuento["avisos"] == ["sin_narracion"]
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    llamadas_texto = entorno.c.texto.llamadas_cuento

    entorno.c.voz.fallar = False
    r = entorno.cliente.post(f"/v1/cuentos/{cuento_id}/narracion", headers=cab)
    assert r.status_code == 200
    assert r.json()["avisos"] == []
    assert all(p["audio_url"] for p in r.json()["paginas"])
    assert entorno.c.texto.llamadas_cuento == llamadas_texto  # no se rehízo el cuento


def test_reintento_por_paso_sin_rehacer_el_cuento(entorno):
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.fallos_pendientes = 1
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    assert _cuento(entorno, cab, cuento_id)["estado"] == "listo"
    pasos, _ = _pasos(entorno, admin, cuento_id)
    assert pasos["escribir"]["intentos"] == 2
    assert pasos["escenarios"]["intentos"] == 3


def test_sin_cuento_no_hay_nada_que_mostrar(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.fallar = True
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = _cuento(entorno, cab, cuento_id)
    assert cuento["estado"] == "fallido"
    assert cuento["paginas"] == []
    assert entorno.c.almacen.objetos == {}
    assert entorno.c.imagen.llamadas == 0 and entorno.c.voz.llamadas == 0


def test_perfil_ajeno(entorno):
    cab = entorno.registrar("a@correo.com")
    otro = entorno.registrar("b@correo.com")
    perfil = entorno.crear_perfil(cab)
    assert entorno.crear_cuento(otro, perfil).status_code == 404
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    assert entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=otro).status_code == 404
