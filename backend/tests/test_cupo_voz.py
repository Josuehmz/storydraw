"""Voz limitada en el plan gratuito: tope diario de cuentos con voz y reserva ante un 429.

Decisión de Josue (2026-11-09): «Se enciende limitada, se permanece en plan gratuito». El tope
(`VOZ_CUENTOS_POR_DIA`, 3 por defecto) se cuenta en la base de datos por día UTC, que es cuando
Cloudflare repone sus 10.000 neuronas gratis. Pasado el tope, el cuento sale sin voz y sin error.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx
import pytest

from app.dominio.orquestador import AVISO_SIN_NARRACION, AVISO_VOZ_SIN_CUPO
from app.dominio.puertos import CupoAgotado
from app.infra.adaptadores.proveedor_cloudflare import ClienteCloudflare, CupoAgotadoCloudflare
from app.infra.bd import crear_fabrica, crear_motor
from app.infra.cupo_voz import SIN_TOPE, CupoVozBD, consulta_reserva
from app.infra.orm import Base


class Reloj:
    """Día UTC que la prueba puede adelantar."""

    def __init__(self, dia: date = date(2026, 11, 9)):
        self.dia = dia

    def __call__(self) -> date:
        return self.dia

    def manana(self) -> None:
        self.dia += timedelta(days=1)


async def _fabrica(ruta):
    motor = crear_motor(f"sqlite+aiosqlite:///{ruta.as_posix()}")
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)
    return motor, crear_fabrica(motor)


# ------------------------------------------------------------------ contador


def test_el_tope_cuenta_cuentos_por_dia_y_luego_dice_que_no(tmp_path):
    async def caso():
        motor, fabrica = await _fabrica(tmp_path / "cupo.db")
        cupo = CupoVozBD(fabrica, 3, Reloj())
        resultados = [await cupo.reservar() for _ in range(5)]
        usados = await cupo.usados_hoy()
        await motor.dispose()
        return resultados, usados

    resultados, usados = asyncio.run(caso())
    assert resultados == [True, True, True, False, False]
    assert usados == 3  # los rechazados no suman


def test_el_tope_se_reinicia_con_el_dia_utc(tmp_path):
    async def caso():
        motor, fabrica = await _fabrica(tmp_path / "cupo.db")
        reloj = Reloj()
        cupo = CupoVozBD(fabrica, 2, reloj)
        hoy = [await cupo.reservar() for _ in range(3)]
        reloj.manana()
        manana = [await cupo.reservar() for _ in range(3)]
        await motor.dispose()
        return hoy, manana

    hoy, manana = asyncio.run(caso())
    assert hoy == [True, True, False]
    assert manana == [True, True, False]


def test_dos_cuentos_a_la_vez_no_se_pasan_del_tope(tmp_path):
    """Muchas reservas simultáneas, desde dos instancias (como dos trabajadores del backend)
    sobre la misma base: la sentencia atómica deja pasar exactamente el tope."""

    async def caso():
        motor, fabrica = await _fabrica(tmp_path / "cupo.db")
        reloj = Reloj()
        uno, otro = CupoVozBD(fabrica, 3, reloj), CupoVozBD(fabrica, 3, reloj)
        resultados = await asyncio.gather(*(c.reservar() for _ in range(6) for c in (uno, otro)))
        usados = await uno.usados_hoy()
        await motor.dispose()
        return resultados, usados

    resultados, usados = asyncio.run(caso())
    assert sum(resultados) == 3 and len(resultados) == 12
    assert usados == 3


def test_liberar_devuelve_la_reserva_sin_bajar_de_cero(tmp_path):
    async def caso():
        motor, fabrica = await _fabrica(tmp_path / "cupo.db")
        cupo = CupoVozBD(fabrica, 1, Reloj())
        assert await cupo.reservar() and not await cupo.reservar()
        await cupo.liberar()
        otra = await cupo.reservar()
        await cupo.liberar()
        await cupo.liberar()  # de más: no queda negativo
        usados = await cupo.usados_hoy()
        await motor.dispose()
        return otra, usados

    otra, usados = asyncio.run(caso())
    assert otra is True and usados == 0


def test_en_postgresql_la_reserva_es_una_sola_sentencia_atomica():
    """Producción usa Neon (PostgreSQL): la misma reserva, compilada para ese dialecto."""
    from sqlalchemy.dialects import postgresql

    sql = str(
        consulta_reserva("postgresql", date(2026, 11, 9), 3).compile(dialect=postgresql.dialect())
    )
    assert "INSERT INTO cupos_voz" in sql
    assert "ON CONFLICT (dia) DO UPDATE SET usados = (cupos_voz.usados + " in sql
    assert "WHERE cupos_voz.usados < " in sql and "RETURNING cupos_voz.usados" in sql


@pytest.mark.parametrize(("tope", "esperado"), [(0, False), (SIN_TOPE, True)])
def test_tope_cero_es_sin_voz_y_menos_uno_sin_limite(tmp_path, tope, esperado):
    async def caso():
        motor, fabrica = await _fabrica(tmp_path / "cupo.db")
        cupo = CupoVozBD(fabrica, tope, Reloj())
        resultados = [await cupo.reservar() for _ in range(10)]
        await motor.dispose()
        return resultados

    assert asyncio.run(caso()) == [esperado] * 10


def test_el_tope_por_defecto_es_tres_y_se_valida(tmp_path):
    from pydantic import ValidationError

    from tests.conftest import settings_de_prueba

    assert settings_de_prueba(tmp_path / "a.db").voz_cuentos_por_dia == 3
    with pytest.raises(ValidationError):
        settings_de_prueba(tmp_path / "a.db", voz_cuentos_por_dia=-2)


# ------------------------------------------------------------------ pipeline


def _cuento(entorno, cab, cuento_id):
    r = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_pasado_el_tope_el_cuento_sale_sin_voz_y_sin_error(crear_entorno):
    entorno = crear_entorno(voz_cuentos_por_dia=1)
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    primero = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert all(p["audio_url"] for p in primero["paginas"])
    assert entorno.c.voz.llamadas == 3

    segundo = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert segundo["estado"] == "listo" and len(segundo["paginas"]) == 3
    # Sin audio, la app no muestra el botón de escuchar (ver cuento_biblioteca_test.dart).
    assert all(p["audio_url"] is None for p in segundo["paginas"])
    # Aviso informativo (la app no lo muestra), no el de «la voz falló».
    assert AVISO_VOZ_SIN_CUPO in segundo["avisos"]
    assert AVISO_SIN_NARRACION not in segundo["avisos"]
    assert entorno.c.voz.llamadas == 3  # ni se llamó: no se gasta cupo


def test_tope_cero_apaga_la_voz_sin_llamarla(crear_entorno):
    entorno = crear_entorno(voz_cuentos_por_dia=0)
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert cuento["estado"] == "listo"
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    assert entorno.c.voz.llamadas == 0


def _voz_sin_cupo(entorno, diario: bool, paginas_bien: int = 0):
    """La voz falsa responde con un 429 (cupo) después de `paginas_bien` audios."""
    original = entorno.c.voz.narrar
    llamadas = {"n": 0}

    async def narrar(texto):
        llamadas["n"] += 1
        if llamadas["n"] > paginas_bien:
            raise CupoAgotado("429 sin cupo", diario=diario)
        return await original(texto)

    entorno.c.voz.narrar = narrar
    return llamadas


def test_un_429_de_la_voz_deja_el_cuento_sin_voz_sin_reintentos(crear_entorno):
    entorno = crear_entorno()
    reloj = Reloj()
    entorno.c.orquestador._reloj = reloj
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    llamadas = _voz_sin_cupo(entorno, diario=True)

    cuento = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert cuento["estado"] == "listo"
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    assert AVISO_VOZ_SIN_CUPO in cuento["avisos"]
    assert llamadas["n"] == 3  # una por página: un 429 no se reintenta
    # El cuento no tuvo voz: su reserva se devolvió.
    assert asyncio.run(entorno.c.orquestador.cupo_voz.usados_hoy()) == 0

    # Mismo día UTC: ni se intenta (el cupo del proveedor ya se acabó).
    cuento = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    assert llamadas["n"] == 3

    # Al día UTC siguiente, se vuelve a intentar.
    reloj.manana()
    _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert llamadas["n"] == 6


def test_un_429_que_no_es_del_cupo_diario_no_apaga_la_voz_el_resto_del_dia(crear_entorno):
    entorno = crear_entorno()
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    llamadas = _voz_sin_cupo(entorno, diario=False)
    _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert llamadas["n"] == 6  # el segundo cuento sí lo intenta


def test_si_el_cupo_se_acaba_a_mitad_del_cuento_sale_entero_sin_voz(crear_entorno):
    entorno = crear_entorno()
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    _voz_sin_cupo(entorno, diario=True, paginas_bien=1)
    cuento = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    # O todas las páginas tienen voz o ninguna: un cuento narrado a medias confunde.
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    assert AVISO_VOZ_SIN_CUPO in cuento["avisos"]


def test_dos_cuentos_simultaneos_con_tope_uno_solo_uno_tiene_voz(crear_entorno):
    entorno = crear_entorno(voz_cuentos_por_dia=1)
    orq = entorno.c.orquestador
    textos = ["Página uno.", "Página dos.", "Página tres."]

    async def caso():
        return await asyncio.gather(orq.narrar(textos, avisos=[]), orq.narrar(textos, avisos=[]))

    uno, otro = asyncio.run(caso())
    con_voz = [a for a in (uno, otro) if all(a)]
    sin_voz = [a for a in (uno, otro) if not any(a)]
    assert len(con_voz) == 1 and len(sin_voz) == 1


def test_sin_base_de_datos_para_el_cupo_no_hay_voz_pero_si_cuento(crear_entorno):
    entorno = crear_entorno()

    class CupoRoto:
        async def reservar(self):
            raise RuntimeError("bd caída")

        async def liberar(self):
            raise RuntimeError("bd caída")

    entorno.c.orquestador.cupo_voz = CupoRoto()
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento = _cuento(entorno, cab, entorno.crear_cuento(cab, perfil).json()["id"])
    assert cuento["estado"] == "listo"
    assert all(p["audio_url"] is None for p in cuento["paginas"])
    assert entorno.c.voz.llamadas == 0


# ------------------------------------------------------------------ Cloudflare 429


def _cliente(estado: int, mensaje: str) -> tuple[httpx.AsyncClient, ClienteCloudflare]:
    def responder(_peticion):
        return httpx.Response(
            estado, json={"success": False, "errors": [{"code": 4006, "message": mensaje}]}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    return http, ClienteCloudflare(http, "cuenta", "token", 10, 0.011, (1.0, 1.0))


@pytest.mark.parametrize(
    ("mensaje", "diario"),
    [
        (
            "AiError: you have used up your daily free allocation of 10,000 neurons, please "
            "upgrade to Cloudflare's Workers Paid plan",
            True,
        ),
        ("Too many requests", False),
    ],
)
def test_cloudflare_429_es_cupo_agotado(mensaje, diario):
    async def caso():
        http, cliente = _cliente(429, mensaje)
        try:
            await cliente.run("@cf/deepgram/aura-2-es", {"text": "Hola."})
        finally:
            await http.aclose()

    with pytest.raises(CupoAgotadoCloudflare) as error:
        asyncio.run(caso())
    assert isinstance(error.value, CupoAgotado) and error.value.diario is diario
