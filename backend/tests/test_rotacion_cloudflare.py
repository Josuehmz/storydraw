"""Rotación de cuentas de Cloudflare Workers AI ante un 429, con HTTP falso (sin red)."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.contenedor import construir
from app.dominio.puertos import CupoAgotado
from app.infra.adaptadores.proveedor_cloudflare import (
    REPRUEBA_TRAS_REPOSICION,
    ClienteCloudflare,
    CuentaCloudflare,
    CupoAgotadoCloudflare,
    _neuronas_de,
)
from tests.conftest import settings_de_prueba

MODELO = "@cf/google/gemma-4-26b-a4b-it"
DIARIO = (
    "AiError: you have used up your daily free allocation of 10,000 neurons, please "
    "upgrade to Cloudflare's Workers Paid plan"
)
ESQUEMA = {"name": "prueba", "schema": {"type": "object"}}


class Reloj:
    def __init__(self, ahora: datetime):
        self.ahora = ahora

    def __call__(self) -> datetime:
        return self.ahora

    def avanzar(self, **delta) -> None:
        self.ahora += timedelta(**delta)


class Cloudflare:
    """Workers AI falso: cada cuenta responde según su modo ("ok", "diario" o "ritmo")."""

    def __init__(self, **modos: str):
        self.modos = modos
        self.peticiones: list[tuple[str, str, bytes]] = []  # (cuenta, token, cuerpo)
        self.retry_after: str | None = None
        self.pausa = 0.0

    async def manejar(self, request: httpx.Request) -> httpx.Response:
        cuenta = request.url.path.split("/accounts/")[1].split("/")[0]
        token = request.headers["authorization"].removeprefix("Bearer ")
        self.peticiones.append((cuenta, token, request.content))
        if self.pausa:
            await asyncio.sleep(self.pausa)
        modo = self.modos[cuenta]
        if modo == "diario":
            return _error_429(DIARIO)
        if modo == "ritmo":
            cabeceras = {"retry-after": self.retry_after} if self.retry_after else {}
            return _error_429("Too many requests", cabeceras)
        return httpx.Response(
            200,
            headers={"cf-ai-neurons": "12.5"},
            json={
                "success": True,
                "result": {
                    "response": '{"ok": true}',
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
                },
            },
        )

    def cuentas(self) -> list[str]:
        return [c for c, _, _ in self.peticiones]


def _error_429(mensaje: str, cabeceras: dict | None = None) -> httpx.Response:
    return httpx.Response(
        429,
        headers=cabeceras or {},
        json={"success": False, "errors": [{"code": 4006, "message": mensaje}]},
    )


def _cliente(
    falso: Cloudflare, n: int = 2, reloj: Reloj | None = None
) -> tuple[httpx.AsyncClient, ClienteCloudflare]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(falso.manejar))
    extra = [CuentaCloudflare(f"c{i}", f"t{i}") for i in range(2, n + 1)]
    cliente = ClienteCloudflare(
        http,
        "c1",
        "t1",
        10,
        0.011,
        (9091.0, 27273.0),
        cuentas_extra=extra,
        reloj=reloj or Reloj(datetime(2026, 11, 19, 15, 0, tzinfo=UTC)),
    )
    return http, cliente


def _correr(falso: Cloudflare, pasos, n: int = 2, reloj: Reloj | None = None):
    async def caso():
        http, cliente = _cliente(falso, n, reloj)
        try:
            return await pasos(cliente)
        finally:
            await http.aclose()

    return asyncio.run(caso())


async def _chat(cliente: ClienteCloudflare):
    return await cliente.chat_json(MODELO, "sistema", "usuario", ESQUEMA, max_tokens=50)


# ------------------------------------------------------------------ rotación por cupo


def test_cuenta_1_agotada_la_2_atiende_la_misma_peticion(caplog):
    falso = Cloudflare(c1="diario", c2="ok")
    caplog.set_level(logging.INFO, logger="app.infra.adaptadores.proveedor_cloudflare")

    async def pasos(cliente):
        primera = await _chat(cliente)
        segunda = await _chat(cliente)  # ya no pasa por la cuenta 1
        return primera, segunda

    (datos, uso), _ = _correr(falso, pasos)
    assert datos == {"ok": True}
    assert falso.cuentas() == ["c1", "c2", "c2"]
    # Misma petición, con el token de la cuenta 2
    assert falso.peticiones[0][2] == falso.peticiones[1][2]
    assert [t for _, t, _ in falso.peticiones] == ["t1", "t2", "t2"]
    # El costo se calcula igual, la atienda la cuenta que la atienda
    assert uso.neuronas == pytest.approx((1000 * 9091 + 100 * 27273) / 1_000_000)
    assert uso.costo_usd == pytest.approx(uso.neuronas / 1000 * 0.011)
    # Log por posición, sin ids ni tokens
    assert "cuenta 1 de 2" in caplog.text and "cuenta 2 de 2" in caplog.text
    for secreto in ("c1", "c2", "t1", "t2"):
        assert f" {secreto}" not in caplog.text and f"/{secreto}" not in caplog.text


def test_las_neuronas_de_cloudflare_se_leen_de_la_cuenta_que_atendio():
    falso = Cloudflare(c1="diario", c2="ok")

    async def pasos(cliente):
        return await cliente.run(MODELO, {"text": "Hola."})

    respuesta = _correr(falso, pasos)
    assert _neuronas_de(respuesta) == 12.5


def test_todas_agotadas_lanza_el_cupo_agotado_de_siempre():
    falso = Cloudflare(c1="diario", c2="diario", c3="diario")
    errores = []

    async def pasos(cliente):
        for _ in range(2):
            with pytest.raises(CupoAgotadoCloudflare) as error:
                await _chat(cliente)
            errores.append(error.value)

    _correr(falso, pasos, n=3)
    assert all(isinstance(e, CupoAgotado) and e.diario for e in errores)
    # La segunda vez ni siquiera llama: todas están apartadas hasta las 00:00 UTC
    assert falso.cuentas() == ["c1", "c2", "c3"]


def test_las_cuentas_se_reponen_al_cambiar_el_dia_utc():
    falso = Cloudflare(c1="diario", c2="ok")
    reloj = Reloj(datetime(2026, 11, 19, 23, 50, tzinfo=UTC))

    async def pasos(cliente):
        await _chat(cliente)  # c1 se agota, atiende c2
        reloj.avanzar(minutes=9)  # 23:59: c1 sigue apartada
        await _chat(cliente)
        falso.modos["c1"] = "ok"
        reloj.avanzar(minutes=2)  # 00:01 del día siguiente: c1 vuelve a ser la primera
        await _chat(cliente)

    _correr(falso, pasos, reloj=reloj)
    assert falso.cuentas() == ["c1", "c2", "c2", "c1"]


def test_si_el_cupo_no_se_repuso_a_medianoche_se_reprueba_cada_media_hora():
    # Ventana móvil de ~24 h (visto el 2026-11-10): no se aparta la cuenta otro día entero.
    falso = Cloudflare(c1="diario", c2="ok")
    reloj = Reloj(datetime(2026, 11, 19, 18, 0, tzinfo=UTC))

    async def pasos(cliente):
        await _chat(cliente)  # c1 agotada hasta las 00:00
        reloj.ahora = datetime(2026, 11, 20, 0, 5, tzinfo=UTC)
        await _chat(cliente)  # c1 aún sin cupo: apartada solo 30 min
        reloj.avanzar(minutes=10)
        await _chat(cliente)  # dentro de los 30 min: directo a c2
        falso.modos["c1"] = "ok"
        reloj.avanzar(seconds=REPRUEBA_TRAS_REPOSICION.total_seconds())
        await _chat(cliente)  # se reprueba c1 y ya responde

    _correr(falso, pasos, reloj=reloj)
    assert falso.cuentas() == ["c1", "c2", "c1", "c2", "c2", "c1"]


def test_una_cuenta_que_se_agota_hoy_por_primera_vez_queda_apartada_hasta_medianoche():
    falso = Cloudflare(c1="diario", c2="ok")
    reloj = Reloj(datetime(2026, 11, 19, 1, 0, tzinfo=UTC))

    async def pasos(cliente):
        await _chat(cliente)
        reloj.avanzar(hours=22, minutes=59)  # 23:59: todavía apartada
        await _chat(cliente)

    _correr(falso, pasos, reloj=reloj)
    assert falso.cuentas() == ["c1", "c2", "c2"]


# ------------------------------------------------------------------ 429 de ritmo


def test_429_de_ritmo_pasa_a_la_siguiente_sin_dar_la_cuenta_por_agotada():
    falso = Cloudflare(c1="ritmo", c2="ok")
    reloj = Reloj(datetime(2026, 11, 19, 15, 0, tzinfo=UTC))

    async def pasos(cliente):
        await _chat(cliente)  # c1 limitada: atiende c2 y c1 se aparta 60 s
        reloj.avanzar(seconds=30)
        await _chat(cliente)
        falso.modos["c1"] = "ok"
        reloj.avanzar(seconds=31)  # pasó el minuto: c1 vuelve a ser la primera
        await _chat(cliente)

    _correr(falso, pasos, reloj=reloj)
    assert falso.cuentas() == ["c1", "c2", "c2", "c1"]


def test_429_de_ritmo_respeta_retry_after():
    falso = Cloudflare(c1="ritmo", c2="ok")
    falso.retry_after = "5"
    reloj = Reloj(datetime(2026, 11, 19, 15, 0, tzinfo=UTC))

    async def pasos(cliente):
        await _chat(cliente)
        falso.modos["c1"] = "ok"
        reloj.avanzar(seconds=6)
        await _chat(cliente)

    _correr(falso, pasos, reloj=reloj)
    assert falso.cuentas() == ["c1", "c2", "c1"]


def test_ritmo_en_todas_lanza_cupo_no_diario_y_las_sigue_probando():
    falso = Cloudflare(c1="ritmo", c2="ritmo")

    async def pasos(cliente):
        for _ in range(2):
            with pytest.raises(CupoAgotadoCloudflare) as error:
                await _chat(cliente)
            assert error.value.diario is False

    _correr(falso, pasos)
    # Un límite de ritmo no aparta la cuenta: la siguiente petición las vuelve a intentar
    assert falso.cuentas() == ["c1", "c2", "c1", "c2"]


# ------------------------------------------------------------------ una sola cuenta


def test_una_sola_cuenta_se_comporta_como_antes():
    falso = Cloudflare(c1="ok")

    async def pasos(cliente):
        assert cliente.total_cuentas == 1
        return await _chat(cliente)

    datos, uso = _correr(falso, pasos, n=1)
    assert datos == {"ok": True} and uso.neuronas > 0
    assert falso.cuentas() == ["c1"]

    falso = Cloudflare(c1="ritmo")

    async def ritmo(cliente):
        for _ in range(2):  # como antes: cada petición llama y falla con cupo no diario
            with pytest.raises(CupoAgotadoCloudflare) as error:
                await _chat(cliente)
            assert error.value.diario is False

    _correr(falso, ritmo, n=1)
    assert falso.cuentas() == ["c1", "c1"]

    falso = Cloudflare(c1="diario")

    async def diario(cliente):
        with pytest.raises(CupoAgotadoCloudflare) as error:
            await _chat(cliente)
        assert error.value.diario is True and "daily free allocation" in str(error.value)

    _correr(falso, diario, n=1)


def test_un_timeout_no_cambia_de_cuenta():
    peticiones = []

    def manejar(request):
        peticiones.append(request)
        raise httpx.ReadTimeout("lento", request=request)

    async def caso():
        http = httpx.AsyncClient(transport=httpx.MockTransport(manejar))
        cliente = ClienteCloudflare(
            http, "c1", "t1", 1, 0.011, (1.0, 1.0), cuentas_extra=[CuentaCloudflare("c2", "t2")]
        )
        try:
            with pytest.raises(TimeoutError):
                await cliente.run(MODELO, {})
        finally:
            await http.aclose()

    asyncio.run(caso())
    assert len(peticiones) == 1


# ------------------------------------------------------------------ concurrencia


def test_dos_cuentos_a_la_vez_no_corrompen_el_estado(caplog):
    falso = Cloudflare(c1="diario", c2="ok")
    falso.pausa = 0.01  # las peticiones se solapan de verdad
    caplog.set_level(logging.WARNING, logger="app.infra.adaptadores.proveedor_cloudflare")

    async def pasos(cliente):
        resultados = await asyncio.gather(*(_chat(cliente) for _ in range(20)))
        despues = await _chat(cliente)
        return resultados, despues

    resultados, _ = _correr(falso, pasos)
    assert len(resultados) == 20 and all(d == {"ok": True} for d, _ in resultados)
    assert falso.cuentas().count("c2") == 21
    assert falso.cuentas()[-1] == "c2"
    # La cuenta 1 se marca una sola vez aunque varias peticiones vieran su 429 a la vez
    assert caplog.text.count("cupo diario agotado en la cuenta 1 de 2") == 1


def test_el_estado_aguanta_hilos_a_la_vez():
    reloj = Reloj(datetime(2026, 11, 19, 15, 0, tzinfo=UTC))
    cliente = ClienteCloudflare(
        None,  # type: ignore[arg-type]
        "c1",
        "t1",
        1,
        0.011,
        (1.0, 1.0),
        cuentas_extra=[CuentaCloudflare("c2", "t2")],
        reloj=reloj,
    )
    elegidas: list[int | None] = []

    def golpear():
        for _ in range(200):
            cliente._marcar_agotada(0)
            elegidas.append(cliente._elegir(set()))

    hilos = [threading.Thread(target=golpear) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert set(elegidas) == {1}


# ------------------------------------------------------------------ configuración


def _base(**cambios) -> Settings:
    datos = dict(
        jwt_secreto="s" * 48,
        proveedor_vision="falso",
        proveedor_texto="cloudflare",
        proveedor_moderacion="falso",
        proveedor_imagen="falso",
        proveedor_correo="falso",
        almacen="memoria",
        cloudflare_account_id="c1",
        cloudflare_api_token="t1",
    )
    datos.update(cambios)
    return Settings(_env_file=None, **datos)


def test_configuracion_de_cuentas_extra():
    assert _base().cuentas_cloudflare_extra == []
    s = _base(
        cloudflare_account_id_2="c2",
        cloudflare_api_token_2="t2",
        cloudflare_account_id_3="c3",
        cloudflare_api_token_3="t3",
    )
    assert [(c, t.get_secret_value()) for c, t in s.cuentas_cloudflare_extra] == [
        ("c2", "t2"),
        ("c3", "t3"),
    ]
    assert "t2" not in repr(s)


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"cloudflare_account_id_2": "c2"}, "CLOUDFLARE_API_TOKEN_2"),
        ({"cloudflare_api_token_3": "t3"}, "CLOUDFLARE_ACCOUNT_ID_3"),
        (
            {
                "cloudflare_account_id": "",
                "cloudflare_api_token": None,
                "proveedor_texto": "falso",
                "cloudflare_account_id_2": "c2",
                "cloudflare_api_token_2": "t2",
            },
            "la cuenta 1",
        ),
        ({"cloudflare_account_id_2": "c1", "cloudflare_api_token_2": "t2"}, "repetida"),
    ],
)
def test_configuracion_incompleta_falla_al_arrancar(cambios, mensaje):
    with pytest.raises(ValidationError, match=mensaje):
        _base(**cambios)


def test_el_contenedor_arma_el_cliente_con_todas_las_cuentas(tmp_path: Path):
    settings = settings_de_prueba(
        tmp_path / "bd.sqlite",
        proveedor_texto="cloudflare",
        cloudflare_account_id="c1",
        cloudflare_api_token="t1",
        cloudflare_account_id_2="c2",
        cloudflare_api_token_2="t2",
    )
    c = construir(settings)
    try:
        assert c.texto._cliente.total_cuentas == 2  # type: ignore[attr-defined]
    finally:
        asyncio.run(c.cerrar())
