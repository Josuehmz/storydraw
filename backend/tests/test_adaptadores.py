"""Adaptadores reales contra un transporte HTTP simulado: valida la forma de cada petición
(endpoint, modelo, parámetros) y la lectura de la respuesta, sin red ni claves reales."""

from __future__ import annotations

import base64
import json

import httpx2
import pytest
from openai import AsyncOpenAI

from app.dominio.puertos import SolicitudCuento
from app.infra.adaptadores.comun import mensaje_solicitud, prompt_fondo
from app.infra.adaptadores.proveedor_openai import ImagenOpenAI, TextoOpenAI, VisionOpenAI

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _chat(contenido: dict) -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-5.6-luna",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(contenido)},
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


def _cliente(peticiones: list, respuesta: dict) -> AsyncOpenAI:
    def manejar(request: httpx2.Request) -> httpx2.Response:
        peticiones.append((request.url.path, json.loads(request.content)))
        return httpx2.Response(200, json=respuesta)

    return AsyncOpenAI(
        api_key="clave-de-prueba",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(manejar)),
        max_retries=0,
    )


async def test_vision_openai():
    peticiones: list = []
    cliente = _cliente(
        peticiones, _chat({"hipotesis": [{"etiqueta": "un gato", "confianza": 0.7}]})
    )
    res = await VisionOpenAI(cliente, "gpt-5.6-luna", "low").identificar(b"\x89PNG")
    ruta, cuerpo = peticiones[0]
    assert ruta.endswith("/chat/completions")
    assert cuerpo["model"] == "gpt-5.6-luna" and cuerpo["reasoning_effort"] == "low"
    assert cuerpo["response_format"]["type"] == "json_schema"
    imagen = cuerpo["messages"][1]["content"][1]["image_url"]["url"]
    assert imagen.startswith("data:image/png;base64,")
    assert res.hipotesis[0].etiqueta == "un gato" and res.uso.tokens_entrada == 120


async def test_texto_openai_cuento_sin_datos_del_nino():
    peticiones: list = []
    paginas = [{"texto": f"Página {i}", "escena": "a meadow"} for i in range(3)]
    cliente = _cliente(peticiones, _chat({"titulo": "El gato", "paginas": paginas}))
    texto = TextoOpenAI(cliente, "gpt-5.6-luna", "omni-moderation-latest")
    cuento = await texto.escribir_cuento(SolicitudCuento("un gato", 9))
    _, cuerpo = peticiones[0]
    sistema = cuerpo["messages"][0]["content"]
    assert "un gato" in sistema and "9 años" in sistema
    assert "reasoning_effort" not in cuerpo  # vacío = no se envía
    assert cuento.titulo == "El gato" and len(cuento.paginas) == 3
    assert cuento.uso.tokens_salida == 30


async def test_moderacion_openai():
    peticiones: list = []
    categorias = {"violence": True, "sexual": False, "hate": False}
    cliente = _cliente(
        peticiones,
        {
            "id": "modr-1",
            "model": "omni-moderation-latest",
            "results": [
                {
                    "flagged": True,
                    "categories": categorias,
                    "category_scores": {k: 0.9 if v else 0.0 for k, v in categorias.items()},
                    "category_applied_input_types": {k: ["text"] for k in categorias},
                }
            ],
        },
    )
    veredicto = await TextoOpenAI(cliente, "m", "omni-moderation-latest").moderar("texto")
    ruta, cuerpo = peticiones[0]
    assert ruta.endswith("/moderations") and cuerpo["model"] == "omni-moderation-latest"
    assert veredicto.aprobado is False and "violence" in veredicto.categorias


async def test_imagen_openai():
    peticiones: list = []
    png = base64.b64encode(b"\x89PNG-falso").decode()
    cliente = _cliente(peticiones, {"created": 0, "data": [{"b64_json": png}]})
    res = await ImagenOpenAI(cliente, "gpt-image-1-mini", "low", "1024x1024").generar_fondo("sea")
    ruta, cuerpo = peticiones[0]
    assert ruta.endswith("/images/generations")
    assert cuerpo["model"] == "gpt-image-1-mini"
    assert cuerpo["quality"] == "low" and cuerpo["size"] == "1024x1024"
    assert cuerpo["prompt"] == prompt_fondo("sea")  # sin copia propia del prompt
    assert res.png == b"\x89PNG-falso" and res.uso.imagenes == 1


def test_prompt_fondo_estilo_lapices_de_colores():
    prompt = prompt_fondo("a quiet river in a forest")
    assert "colored pencil" in prompt.lower() and "crayon" in prompt.lower()
    assert "not photorealistic" in prompt and "not 3D" in prompt
    assert "Scene: a quiet river in a forest." in prompt
    assert "no people" in prompt and "no animals" in prompt and "no text" in prompt


def test_regla_de_escenas_coherente_con_el_protagonista_y_estilo_coherente():
    mensaje = mensaje_solicitud(SolicitudCuento("un carro", 7))
    assert "sin personajes, personas, animales ni texto" in mensaje
    assert "un carro en una carretera, un pez en el mar" in mensaje
    assert "una obra de construcción" in mensaje
    assert "misma paleta de colores" in mensaje


def test_nombre_del_personaje_va_al_prompt_del_cuento():
    con = mensaje_solicitud(SolicitudCuento("un perro", 7, nombre="Rayo"))
    assert "se llama «Rayo»" in con
    sin = mensaje_solicitud(SolicitudCuento("un perro", 7))
    assert "«" not in sin.split("7. ")[1]
