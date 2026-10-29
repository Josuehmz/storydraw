"""Proveedores gratuitos (Ollama y Cloudflare Workers AI) contra HTTP simulado: forma de
cada petición, lectura de la respuesta, errores y timeouts. Y la moderación con LLM, que
es solo para desarrollo y tiene que fallar cerrada."""

from __future__ import annotations

import asyncio
import base64
import io
import json

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.config import Settings
from app.dominio.moderacion import Moderacion
from app.dominio.puertos import SolicitudCuento
from app.infra.adaptadores.comun import ESQUEMA_CUENTO, ErrorProveedor
from app.infra.adaptadores.falsos import TextoFalso
from app.infra.adaptadores.moderacion_llm import ModeracionLLMSoloDesarrollo
from app.infra.adaptadores.proveedor_cloudflare import (
    ClienteCloudflare,
    ImagenCloudflare,
    TextoCloudflare,
    VisionCloudflare,
)
from app.infra.adaptadores.proveedor_ollama import ClienteOllama, TextoOllama, VisionOllama

PAGINAS = [{"texto": f"Página {i} del cuento.", "escena": "a sunny meadow"} for i in range(3)]
CUENTO = {"titulo": "El dragón amable", "paginas": PAGINAS}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _http(manejar) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(manejar))


def _grabador(respuesta: httpx.Response | Exception):
    peticiones: list[httpx.Request] = []

    def manejar(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    return peticiones, manejar


# ------------------------------------------------------------------ Ollama


def _ollama_ok(contenido: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "llama3.2:3b",
            "message": {"role": "assistant", "content": contenido},
            "done": True,
            "prompt_eval_count": 210,
            "eval_count": 380,
        },
    )


@pytest.mark.anyio
async def test_texto_ollama_forma_del_pedido_y_parseo():
    peticiones, manejar = _grabador(_ollama_ok(json.dumps(CUENTO)))
    async with _http(manejar) as http:
        cliente = ClienteOllama(http, "http://host.docker.internal:11434/", timeout_s=900)
        cuento = await TextoOllama(cliente, "llama3.2:3b").escribir_cuento(
            SolicitudCuento("un dragón", 8)
        )
    req = peticiones[0]
    cuerpo = json.loads(req.content)
    assert str(req.url) == "http://host.docker.internal:11434/api/chat"
    assert cuerpo["model"] == "llama3.2:3b" and cuerpo["stream"] is False
    assert cuerpo["format"] == ESQUEMA_CUENTO["schema"]  # salida estructurada
    paginas = cuerpo["format"]["properties"]["paginas"]
    assert paginas["minItems"] == paginas["maxItems"] == 3  # exactamente 3 páginas
    assert "un dragón" in cuerpo["messages"][0]["content"]
    assert "8 años" in cuerpo["messages"][0]["content"]
    assert req.extensions["timeout"]["read"] == 900  # timeout propio, configurable
    assert cuento.titulo == "El dragón amable" and len(cuento.paginas) == 3
    assert cuento.uso.tokens_entrada == 210 and cuento.uso.tokens_salida == 380
    assert cuento.uso.costo_usd == 0.0  # Ollama no cobra


@pytest.mark.anyio
async def test_texto_ollama_tolera_json_en_bloque_de_codigo():
    contenido = "Aquí está:\n```json\n" + json.dumps(CUENTO) + "\n```"
    _, manejar = _grabador(_ollama_ok(contenido))
    async with _http(manejar) as http:
        cliente = ClienteOllama(http, "http://localhost:11434", 60)
        cuento = await TextoOllama(cliente, "m").escribir_cuento(SolicitudCuento("un gato", 7))
    assert len(cuento.paginas) == 3


@pytest.mark.anyio
async def test_vision_ollama_envia_la_imagen_en_base64():
    hipotesis = {"hipotesis": [{"etiqueta": "un gato", "confianza": 0.8}]}
    peticiones, manejar = _grabador(_ollama_ok(json.dumps(hipotesis)))
    async with _http(manejar) as http:
        cliente = ClienteOllama(http, "http://localhost:11434", 600)
        vision = VisionOllama(cliente, "qwen2.5vl:3b")
        res = await vision.identificar(b"\x89PNG-dibujo")
    cuerpo = json.loads(peticiones[0].content)
    assert cuerpo["model"] == "qwen2.5vl:3b"
    assert cuerpo["messages"][1]["images"] == [base64.b64encode(b"\x89PNG-dibujo").decode()]
    assert res.hipotesis[0].etiqueta == "un gato" and vision.timeout_s == 600


@pytest.mark.anyio
@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(404, json={"error": "model 'qwen2.5vl:3b' not found"}),
        httpx.Response(500, text="fallo interno"),
        _ollama_ok("esto no es JSON"),
        _ollama_ok(""),
    ],
)
async def test_ollama_errores_lanzan(respuesta):
    _, manejar = _grabador(respuesta)
    async with _http(manejar) as http:
        cliente = ClienteOllama(http, "http://localhost:11434", 60)
        with pytest.raises(ErrorProveedor):
            await VisionOllama(cliente, "qwen2.5vl:3b").identificar(b"png")


@pytest.mark.anyio
async def test_ollama_timeout_se_propaga():
    _, manejar = _grabador(httpx.ReadTimeout("lento"))
    async with _http(manejar) as http:
        cliente = ClienteOllama(http, "http://localhost:11434", 1)
        with pytest.raises(httpx.TimeoutException):
            await TextoOllama(cliente, "m").escribir_cuento(SolicitudCuento("un gato", 7))


# ------------------------------------------------------------------ Cloudflare


def _cf(http: httpx.AsyncClient, **cambios) -> ClienteCloudflare:
    datos = dict(
        http=http,
        cuenta="cuenta123",
        token="token-de-prueba",
        timeout_s=120,
        usd_por_mil_neuronas=0.011,
        neuronas_texto_mtok=(9091.0, 27273.0),
    )
    datos.update(cambios)
    return ClienteCloudflare(**datos)


def _sobre(resultado) -> httpx.Response:
    return httpx.Response(
        200, json={"success": True, "errors": [], "messages": [], "result": resultado}
    )


def _ruta(modelo: str) -> str:
    return f"/client/v4/accounts/cuenta123/ai/run/{modelo}"


@pytest.mark.anyio
async def test_texto_cloudflare_formato_chat_completions_y_costo_en_neuronas():
    resultado = {
        "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(CUENTO)}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
    }
    peticiones, manejar = _grabador(_sobre(resultado))
    modelo = "@cf/google/gemma-4-26b-a4b-it"
    async with _http(manejar) as http:
        cuento = await TextoCloudflare(_cf(http), modelo).escribir_cuento(
            SolicitudCuento("un dragón", 9)
        )
    req = peticiones[0]
    cuerpo = json.loads(req.content)
    assert req.url.host == "api.cloudflare.com" and req.url.path == _ruta(modelo)
    assert req.headers["authorization"] == "Bearer token-de-prueba"
    assert cuerpo["response_format"]["type"] == "json_schema"
    assert cuerpo["max_tokens"] >= 1000  # el valor por defecto de Workers AI (256) no alcanza
    assert cuerpo["chat_template_kwargs"] == {"enable_thinking": False}
    assert req.extensions["timeout"]["read"] == 120
    assert len(cuento.paginas) == 3
    neuronas = (1000 * 9091 + 1000 * 27273) / 1_000_000
    assert cuento.uso.neuronas == pytest.approx(neuronas)
    assert cuento.uso.costo_usd == pytest.approx(neuronas / 1000 * 0.011)


@pytest.mark.anyio
async def test_texto_cloudflare_formato_response_ya_parseado_y_sin_razonamiento():
    peticiones, manejar = _grabador(_sobre({"response": CUENTO, "usage": {}}))
    async with _http(manejar) as http:
        cliente = _cf(http, desactivar_razonamiento=False)
        cuento = await TextoCloudflare(cliente, "@cf/meta/llama-3.3-70b").escribir_cuento(
            SolicitudCuento("un gato", 6)
        )
    assert "chat_template_kwargs" not in json.loads(peticiones[0].content)
    assert cuento.titulo == "El dragón amable" and cuento.uso.costo_usd == 0.0


@pytest.mark.anyio
async def test_vision_cloudflare_imagen_como_data_url_y_tarifa_de_vision():
    contenido = json.dumps({"hipotesis": [{"etiqueta": "un cohete", "confianza": 0.9}]})
    resultado = {
        "response": contenido,
        "usage": {"prompt_tokens": 2000, "completion_tokens": 0},
    }
    peticiones, manejar = _grabador(_sobre(resultado))
    async with _http(manejar) as http:
        vision = VisionCloudflare(_cf(http), "@cf/google/gemma-4-26b-a4b-it", (5000.0, 0.0))
        res = await vision.identificar(b"\x89PNG")
    partes = json.loads(peticiones[0].content)["messages"][1]["content"]
    assert partes[0]["type"] == "text"
    assert partes[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert res.hipotesis[0].etiqueta == "un cohete"
    assert res.uso.neuronas == pytest.approx(10.0)


def _jpeg(ancho: int = 1024, alto: int = 1024) -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (ancho, alto), (120, 180, 230)).save(salida, format="JPEG")
    return salida.getvalue()


@pytest.mark.anyio
async def test_imagen_cloudflare_flux_base64_a_png_y_neuronas():
    peticiones, manejar = _grabador(_sobre({"image": base64.b64encode(_jpeg()).decode()}))
    modelo = "@cf/black-forest-labs/flux-1-schnell"
    async with _http(manejar) as http:
        imagen = ImagenCloudflare(_cf(http), modelo, 4, 4.80, 9.60)
        res = await imagen.generar_fondo("a quiet beach at sunset")
    req = peticiones[0]
    cuerpo = json.loads(req.content)
    assert req.url.path == _ruta(modelo)
    assert cuerpo["steps"] == 4 and "a quiet beach at sunset" in cuerpo["prompt"]
    assert set(cuerpo) == {"prompt", "steps"}  # el esquema de flux no admite más campos
    assert "colored pencil" in cuerpo["prompt"].lower()
    assert "not photorealistic" in cuerpo["prompt"]
    assert res.png.startswith(b"\x89PNG")  # el puerto promete PNG
    assert res.uso.neuronas == pytest.approx(4 * 4.80 + 4 * 9.60)  # 4 teselas + 4 pasos
    assert res.uso.costo_usd == pytest.approx(57.6 / 1000 * 0.011)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(
            401, json={"success": False, "errors": [{"code": 10000, "message": "auth"}]}
        ),
        httpx.Response(429, json={"success": False, "errors": [{"message": "neuronas agotadas"}]}),
        httpx.Response(200, json={"success": False, "errors": [{"message": "x"}], "result": None}),
        _sobre({"image": "%%%no-es-base64%%%"}),
        _sobre({"image": base64.b64encode(b"no es una imagen").decode()}),
        _sobre({}),
    ],
)
async def test_imagen_cloudflare_errores_lanzan(respuesta):
    _, manejar = _grabador(respuesta)
    async with _http(manejar) as http:
        imagen = ImagenCloudflare(_cf(http), "@cf/black-forest-labs/flux-1-schnell", 4, 4.8, 9.6)
        with pytest.raises(ErrorProveedor):
            await imagen.generar_fondo("sea")


@pytest.mark.anyio
async def test_cloudflare_error_no_filtra_el_token():
    _, manejar = _grabador(httpx.Response(403, json={"errors": [{"message": "prohibido"}]}))
    async with _http(manejar) as http:
        with pytest.raises(ErrorProveedor) as exc:
            await TextoCloudflare(_cf(http), "m").escribir_cuento(SolicitudCuento("x", 7))
    assert "prohibido" in str(exc.value) and "token-de-prueba" not in str(exc.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "respuesta",
    [
        _sobre({"response": "no hay JSON aquí"}),
        _sobre({"choices": []}),
        httpx.Response(200, text="<html>"),
    ],
)
async def test_texto_cloudflare_respuestas_ilegibles_lanzan(respuesta):
    _, manejar = _grabador(respuesta)
    async with _http(manejar) as http:
        with pytest.raises(ErrorProveedor):
            await TextoCloudflare(_cf(http), "m").escribir_cuento(SolicitudCuento("x", 7))


@pytest.mark.anyio
async def test_cloudflare_timeout_se_propaga():
    _, manejar = _grabador(httpx.ConnectTimeout("sin red"))
    async with _http(manejar) as http:
        # Se vuelve TimeoutError: el orquestador lo reintenta una sola vez
        with pytest.raises(TimeoutError):
            await TextoCloudflare(_cf(http), "m").escribir_cuento(SolicitudCuento("x", 7))


# ------------------------------------------------------------------ Moderación con LLM


def _moderador(respuesta: httpx.Response | Exception, http_holder: list):
    peticiones, manejar = _grabador(respuesta)
    http = _http(manejar)
    http_holder.append(http)
    return peticiones, ModeracionLLMSoloDesarrollo(
        ClienteOllama(http, "http://localhost:11434", 30), "llama3.2:3b"
    )


@pytest.mark.anyio
async def test_moderacion_llm_aprueba_solo_con_apto_true():
    abiertos: list = []
    peticiones, mod = _moderador(_ollama_ok('{"apto": true, "categorias": []}'), abiertos)
    veredicto = await mod.moderar("Había una vez un gato feliz.")
    cuerpo = json.loads(peticiones[0].content)
    assert "gato feliz" in cuerpo["messages"][1]["content"]
    assert cuerpo["format"]["required"] == ["apto", "categorias"]
    assert veredicto.aprobado is True and mod.proveedor == "ollama-llm-dev"
    for http in abiertos:
        await http.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("contenido", "categorias"),
    [
        ('{"apto": false, "categorias": ["violencia"]}', ["llm:violencia"]),
        ('{"apto": false, "categorias": []}', ["llm:no_apto"]),
        ('{"apto": "true", "categorias": []}', ["llm:no_apto"]),  # solo el booleano aprueba
    ],
)
async def test_moderacion_llm_rechaza(contenido, categorias):
    abiertos: list = []
    _, mod = _moderador(_ollama_ok(contenido), abiertos)
    veredicto = await mod.moderar("texto")
    assert veredicto.aprobado is False and veredicto.categorias == categorias
    for http in abiertos:
        await http.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.ReadTimeout("no responde"),
        httpx.ConnectError("Ollama apagado"),
        httpx.Response(500, json={"error": "sin memoria"}),
        _ollama_ok("Claro, el texto es apto."),
        _ollama_ok('{"categorias": []}'),
    ],
)
async def test_moderacion_llm_falla_cerrada_lanzando(respuesta):
    abiertos: list = []
    _, mod = _moderador(respuesta, abiertos)
    with pytest.raises((ErrorProveedor, httpx.HTTPError)):
        await mod.moderar("texto")
    for http in abiertos:
        await http.aclose()


def test_moderacion_llm_caida_el_cuento_no_se_muestra(crear_entorno):
    entorno = crear_entorno()
    cab = entorno.registrar("a@correo.com")
    admin = entorno.registrar("admin@storydraw.com")
    perfil = entorno.crear_perfil(cab)
    _, manejar = _grabador(httpx.ReadTimeout("el LLM no responde"))
    cliente = ClienteOllama(_http(manejar), "http://localhost:11434", 30)
    entorno.c.orquestador.moderacion = Moderacion(
        ModeracionLLMSoloDesarrollo(cliente, "llama3.2:3b")
    )

    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "rechazado" and cuento["paginas"] == []
    assert entorno.c.texto.llamadas_cuento == 0  # ni siquiera se escribió
    cola = entorno.cliente.get("/v1/operacion/moderacion", headers=admin).json()
    assert cola[0]["categorias"] == ["moderacion_no_disponible"]
    panel = entorno.cliente.get("/v1/operacion/cuentos", headers=admin).json()
    pasos = {p["paso"]: p for p in panel[0]["pasos"]}
    assert pasos["moderar"]["proveedor"] == "ollama-llm-dev"
    assert pasos["moderar"]["estado"] == "fallido"


# ------------------------------------------------------------------ Orquestador y configuración


def test_orquestador_respeta_el_timeout_propio_del_adaptador(crear_entorno):
    """Ollama por CPU tarda minutos: el timeout global no lo corta si el adaptador trae uno."""

    class TextoLento(TextoFalso):
        timeout_s = 5.0

        async def escribir_cuento(self, solicitud):
            await asyncio.sleep(0.3)
            return await super().escribir_cuento(solicitud)

    entorno = crear_entorno(timeout_proveedor_s=0.1)
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    entorno.c.orquestador.texto = TextoLento()
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo"


def test_perfil_local_ollama_sin_imagen_degrada(crear_entorno):
    entorno = crear_entorno(proveedor_imagen="ninguno")
    cab = entorno.registrar("a@correo.com")
    perfil = entorno.crear_perfil(cab)
    cuento_id = entorno.crear_cuento(cab, perfil).json()["id"]
    cuento = entorno.cliente.get(f"/v1/cuentos/{cuento_id}", headers=cab).json()
    assert cuento["estado"] == "listo" and len(cuento["paginas"]) == 3
    assert cuento["avisos"] == ["sin_escenarios"]


def test_contenedor_arma_los_proveedores_gratuitos(crear_entorno):
    entorno = crear_entorno(
        proveedor_vision="ollama",
        proveedor_texto="ollama",
        proveedor_moderacion="ollama",
        ollama_timeout_s=1200,
    )
    salud = entorno.cliente.get("/salud").json()["proveedores"]
    assert salud["vision"] == "ollama" and salud["texto"] == "ollama"
    assert salud["moderacion"] == "ollama-llm-dev"
    assert entorno.c.texto.timeout_s == 1200


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


def test_configuracion_de_proveedores_gratuitos():
    with pytest.raises(ValidationError, match="CLOUDFLARE_ACCOUNT_ID"):
        _base(proveedor_imagen="cloudflare")
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        _base(proveedor_moderacion="openai")
    s = _base(proveedor_texto="cloudflare", cloudflare_account_id="c", cloudflare_api_token="t")
    assert s.cloudflare_modelo_imagen == "@cf/black-forest-labs/flux-1-schnell"
    s = _base(proveedor_texto="ollama")
    assert s.ollama_modelo_texto == s.ollama_modelo_vision == s.ollama_modelo_moderacion
    assert s.ollama_modelo_texto == "gemma3:4b"


def test_moderacion_llm_prohibida_en_produccion():
    produccion = dict(
        entorno="produccion",
        proveedor_vision="cloudflare",
        proveedor_texto="cloudflare",
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
    for llm in ("ollama", "cloudflare"):
        with pytest.raises(ValidationError, match="solo para desarrollo"):
            _base(**produccion, proveedor_moderacion=llm)
    assert _base(**produccion, proveedor_moderacion="openai", openai_api_key="k")
