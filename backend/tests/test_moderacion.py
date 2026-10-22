"""Moderación obligatoria: corre antes de que el niño vea nada y no se puede apagar."""

from __future__ import annotations

import inspect

import pytest

from app.config import Settings
from app.dominio.moderacion import Moderacion
from app.dominio.orquestador import Orquestador
from app.dominio.puertos import CuentoTexto, Hipotesis, PaginaTexto, Uso
from app.infra.adaptadores.falsos import TextoFalso


def _cuento_malo() -> CuentoTexto:
    paginas = [PaginaTexto("Había mucha violencia en el bosque.", "forest")] * 3
    return CuentoTexto("Un cuento con violencia", paginas, Uso(800, 700))


def _moderacion(entorno, cabeceras):
    r = entorno.cliente.get("/v1/operacion/moderacion", headers=cabeceras)
    assert r.status_code == 200
    return r.json()


def test_cuento_rechazado_no_se_muestra_y_va_a_la_cola(entorno):
    cab = entorno.registrar("a@correo.com")
    revisora = entorno.registrar("revisora@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.cuentos_forzados = [_cuento_malo() for _ in range(3)]

    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "rechazado"
    assert cuento["paginas"] == [] and cuento["titulo"] is None
    # Se regeneró hasta el máximo (1 + 2 regeneraciones) sin exponer nada.
    assert entorno.c.texto.llamadas_cuento == 3
    assert entorno.c.imagen.llamadas == 0
    assert entorno.c.almacen.objetos == {}
    assert (
        entorno.cliente.get(f"/v1/cuentos/{cuento_id}/paginas/1/imagen", headers=cab).status_code
        == 404
    )

    cola = _moderacion(entorno, revisora)
    assert len(cola) == 3
    assert all(r["origen"] == "cuento" and "violencia" in r["texto"] for r in cola)
    assert entorno.cliente.get(f"/v1/perfiles/{perfil}/cuentos", headers=cab).json() == []

    # El equipo de contenido marca como revisado
    r = entorno.cliente.post(f"/v1/operacion/moderacion/{cola[0]['id']}/revisado", headers=revisora)
    assert r.status_code == 204
    assert len(_moderacion(entorno, revisora)) == 2
    # Un tutor normal no ve la cola
    assert entorno.cliente.get("/v1/operacion/moderacion", headers=cab).status_code == 403


def test_regenera_y_entrega_si_el_segundo_intento_pasa(entorno):
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.cuentos_forzados = [_cuento_malo()]
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo"
    assert "violencia" not in " ".join(p["texto"] for p in cuento["paginas"])
    assert len(_moderacion(entorno, admin)) == 1


def test_entrada_del_nino_se_modera_antes_de_escribir(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil, personaje="una pistola").json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "rechazado"
    assert entorno.c.texto.llamadas_cuento == 0


def test_falla_cerrada_si_cae_la_moderacion(entorno):
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.texto.fallar_moderacion = True
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "rechazado"
    assert cuento["paginas"] == []


def test_filtro_local_por_palabra_completa():
    m = Moderacion(TextoFalso())
    assert not m.revisar_local("Tenía una PISTOLA de agua").aprobado
    assert not m.revisar_local("quería matarlo").aprobado
    # Palabras inocentes que contienen un término no se bloquean.
    assert m.revisar_local("Guardó el tesoro en el armario junto a la mata de flores").aprobado


@pytest.mark.anyio
async def test_hipotesis_inapropiadas_no_llegan_al_nino(entorno):
    entorno.c.vision.hipotesis = [Hipotesis("un cuchillo", 0.9), Hipotesis("un gato", 0.5)]
    resultado = await entorno.c.orquestador.identificar(b"png")
    assert [h.etiqueta for h in resultado.hipotesis] == ["un gato"]


def test_no_existe_interruptor_de_moderacion():
    campos = Settings.model_fields
    assert not any("moder" in nombre and campos[nombre].annotation is bool for nombre in campos)
    parametros = inspect.signature(Orquestador.__init__).parameters
    assert parametros["moderacion"].default is inspect.Parameter.empty


@pytest.fixture
def anyio_backend():
    return "asyncio"
