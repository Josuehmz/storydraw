"""Narración por voz: adaptador de Cloudflare (MeloTTS), conversión a MP3 y paso del pipeline.

El adaptador se prueba contra un transporte HTTP simulado (sin red ni claves). El pipeline,
con la voz falsa del contenedor de pruebas.
"""

from __future__ import annotations

import base64
import io
import json
import math
import struct
import wave

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.infra.adaptadores.audio import es_wav, wav_a_mp3
from app.infra.adaptadores.comun import ErrorProveedor
from app.infra.adaptadores.proveedor_cloudflare import ClienteCloudflare, VozCloudflare

MODELO = "@cf/myshell-ai/melotts"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _wav(segundos: float = 1.0, hz: int = 44_100) -> bytes:
    """Un tono de 440 Hz, mono y de 16 bits: lo que devuelve MeloTTS."""
    muestras = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * n / hz)))
        for n in range(int(segundos * hz))
    )
    salida = io.BytesIO()
    with wave.open(salida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(muestras)
    return salida.getvalue()


def _sobre(audio: str | None) -> httpx.Response:
    resultado = {} if audio is None else {"audio": audio}
    return httpx.Response(
        200, json={"success": True, "errors": [], "messages": [], "result": resultado}
    )


def _voz(respuesta: httpx.Response) -> tuple[list[httpx.Request], httpx.AsyncClient, VozCloudflare]:
    peticiones: list[httpx.Request] = []

    def manejar(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return respuesta

    http = httpx.AsyncClient(transport=httpx.MockTransport(manejar))
    cliente = ClienteCloudflare(
        http=http,
        cuenta="cuenta123",
        token="token-de-prueba",
        timeout_s=120,
        usd_por_mil_neuronas=0.011,
        neuronas_texto_mtok=(9091.0, 27273.0),
    )
    return peticiones, http, VozCloudflare(cliente, MODELO, "es", 18.63)


# ------------------------------------------------------------------ conversión


def test_wav_a_mp3_achica_el_audio_y_mide_la_duracion():
    wav = _wav(2.0)
    mp3, segundos = wav_a_mp3(wav)
    assert es_wav(wav) and not es_wav(mp3)
    assert segundos == pytest.approx(2.0)
    assert mp3[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2") or mp3[:3] == b"ID3"
    assert len(mp3) < len(wav) / 8  # 44,1 kHz a 48 kbps


def test_wav_invalido_se_rechaza():
    with pytest.raises(ErrorProveedor):
        wav_a_mp3(b"RIFFno-soy-un-wav")


# ------------------------------------------------------------------ adaptador


@pytest.mark.anyio
async def test_voz_cloudflare_pide_espanol_y_entrega_mp3_con_costo_por_minuto():
    peticiones, http, voz = _voz(_sobre(base64.b64encode(_wav(3.0)).decode()))
    async with http:
        res = await voz.narrar("Había una vez un pececito llamado Burbuja.")
    req = peticiones[0]
    assert req.url.host == "api.cloudflare.com"
    assert req.url.path == f"/client/v4/accounts/cuenta123/ai/run/{MODELO}"
    assert req.headers["authorization"] == "Bearer token-de-prueba"
    assert json.loads(req.content) == {
        "prompt": "Había una vez un pececito llamado Burbuja.",
        "lang": "es",
    }
    assert not es_wav(res.mp3)
    # 3 s de audio = 3/60 de minuto x 18,63 neuronas
    assert res.uso.neuronas == pytest.approx(3 / 60 * 18.63)
    assert res.uso.costo_usd == pytest.approx(3 / 60 * 18.63 / 1000 * 0.011)
    assert res.uso.caracteres == len("Había una vez un pececito llamado Burbuja.")


@pytest.mark.anyio
async def test_voz_cloudflare_deja_pasar_un_audio_que_ya_es_mp3():
    ya_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
    _, http, voz = _voz(_sobre(base64.b64encode(ya_mp3).decode()))
    async with http:
        res = await voz.narrar("Hola.")
    assert res.mp3 == ya_mp3


@pytest.mark.anyio
@pytest.mark.parametrize("audio", [None, "", "esto-no-es-base64!"])
async def test_voz_cloudflare_sin_audio_valido_falla(audio):
    _, http, voz = _voz(_sobre(audio))
    async with http:
        with pytest.raises(ErrorProveedor):
            await voz.narrar("Hola.")


# ------------------------------------------------------------------ pipeline


def _cuento(entorno, cab, cuento_id):
    r = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def _pasos(entorno, admin, cuento_id):
    filas = entorno.cliente.get("/v1/operacion/cuentos", headers=admin).json()
    return {p["paso"]: p for p in next(f for f in filas if f["id"] == cuento_id)["pasos"]}


def test_cada_pagina_sirve_su_propio_audio(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = _cuento(entorno, cab, cuento_id)
    assert entorno.c.voz.llamadas == 3
    for pagina in cuento["paginas"]:
        r = entorno.cliente.get(pagina["audio_url"], headers=cab)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
        # La voz falsa narra el texto de ESA página
        assert pagina["texto"].encode()[:64] in r.content


def test_el_audio_es_del_dueno_del_cuento(entorno):
    cab = entorno.registrar("a@correo.com")
    ajeno = entorno.registrar("b@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    r = entorno.cliente.get(f"/v1/cuentos/{cuento_id}/paginas/1/audio", headers=ajeno)
    assert r.status_code == 404
    r = entorno.cliente.get(f"/v1/cuentos/{cuento_id}/paginas/9/audio", headers=cab)
    assert r.status_code == 404


def test_voz_apagada_el_cuento_sale_escrito_sin_aviso_ni_llamadas(crear_entorno):
    entorno = crear_entorno(proveedor_voz="ninguno")
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = _cuento(entorno, cab, cuento_id)
    assert cuento["estado"] == "listo" and cuento["avisos"] == []
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    pasos = _pasos(entorno, admin, cuento_id)
    assert pasos["narrar"]["estado"] == "omitido" and pasos["narrar"]["intentos"] == 0
    r = entorno.cliente.get(f"/v1/cuentos/{cuento_id}/paginas/1/audio", headers=cab)
    assert r.status_code == 404 and r.json()["detail"] == "sin_audio"
    assert entorno.cliente.get("/salud").json()["proveedores"]["voz"] == "ninguno"


def test_si_la_voz_cae_el_cuento_se_entrega_sin_audio_y_con_aviso(entorno):
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.voz.fallar = True
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = _cuento(entorno, cab, cuento_id)
    assert cuento["estado"] == "listo" and len(cuento["paginas"]) == 3
    assert cuento["avisos"] == ["sin_narracion"]
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    pasos = _pasos(entorno, admin, cuento_id)
    assert pasos["narrar"]["estado"] == "degradado"
    assert pasos["narrar"]["intentos"] == 6  # 3 páginas x (1 intento + 1 reintento)
    # Las imágenes no se afectan
    img = entorno.cliente.get(cuento["paginas"][0]["imagen_url"], headers=cab)
    assert img.status_code == 200


def test_si_falla_una_sola_pagina_las_otras_conservan_su_audio(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    original = entorno.c.voz.narrar

    async def narrar(texto):
        if "2" in texto:  # solo la página 2 ("Página 2 …")
            entorno.c.voz.fallar = True
        else:
            entorno.c.voz.fallar = False
        return await original(texto)

    entorno.c.voz.narrar = narrar
    entorno.c.texto.cuentos_forzados = [
        _cuento_de_paginas(["Página 1 del cuento.", "Página 2 del cuento.", "Página 3 del cuento."])
    ]
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    audios = [p["audio_url"] for p in _cuento(entorno, cab, cuento_id)["paginas"]]
    assert audios[0] and audios[2] and audios[1] is None


def _cuento_de_paginas(textos):
    from app.dominio.puertos import CuentoTexto, PaginaTexto, Uso

    return CuentoTexto("La aventura", [PaginaTexto(t, "meadow") for t in textos], Uso(100, 100))


def test_no_se_narra_un_cuento_rechazado(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.cuentos_forzados = [
        _cuento_de_paginas(["Un cuento con violencia y sangre."] * 3) for _ in range(3)
    ]
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    assert _cuento(entorno, cab, cuento_id)["estado"] == "rechazado"
    assert entorno.c.voz.llamadas == 0
    assert entorno.c.almacen.objetos == {}


def test_borrar_el_cuento_borra_tambien_su_audio(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    assert any("/audio/" in k for k in entorno.c.almacen.objetos)
    assert entorno.cliente.delete(f"/v1/cuentos/{cuento_id}", headers=cab).status_code == 204
    assert entorno.c.almacen.objetos == {}


# ------------------------------------------------------------------ configuración


def _base(**cambios) -> Settings:
    datos = dict(
        jwt_secreto="s" * 48,
        proveedor_vision="falso",
        proveedor_texto="falso",
        proveedor_moderacion="falso",
        proveedor_imagen="falso",
        proveedor_correo="falso",
        almacen="memoria",
    )
    datos.update(cambios)
    return Settings(_env_file=None, **datos)


def test_la_voz_viene_apagada_por_defecto():
    s = _base()
    assert s.proveedor_voz == "ninguno"
    assert s.cloudflare_modelo_voz == "@cf/myshell-ai/melotts"
    assert s.cloudflare_idioma_voz == "es"


def test_la_voz_de_cloudflare_pide_credenciales():
    with pytest.raises(ValidationError, match="CLOUDFLARE_ACCOUNT_ID"):
        _base(proveedor_voz="cloudflare")
    assert _base(proveedor_voz="cloudflare", cloudflare_account_id="c", cloudflare_api_token="t")


def test_la_voz_falsa_esta_prohibida_en_produccion():
    produccion = dict(
        entorno="produccion",
        proveedor_vision="cloudflare",
        proveedor_texto="cloudflare",
        proveedor_moderacion="openai",
        openai_api_key="k",
        proveedor_imagen="cloudflare",
        proveedor_correo="smtp",
        smtp_host="smtp.x",
        smtp_remitente="a@x",
        almacen="s3",
        s3_access_key="a",
        s3_secret_key="b",
        cloudflare_account_id="c",
        cloudflare_api_token="t",
    )
    with pytest.raises(ValidationError, match="PROVEEDOR_VOZ"):
        _base(**produccion, proveedor_voz="falso")
    assert _base(**produccion, proveedor_voz="cloudflare")
