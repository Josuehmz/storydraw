"""Despliegue gratuito: Render (Blueprint `render.yaml`, imagen sin rembg), Neon (Postgres) y el
Storage Bucket privado de Hugging Face (S3).

Las pruebas contra MinIO real solo corren si se define STORYDRAW_MINIO_URL (con
STORYDRAW_MINIO_USUARIO y STORYDRAW_MINIO_CLAVE); el resto no toca la red.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest
import yaml
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from app.config import Settings
from app.infra.adaptadores.almacen import AlmacenS3, ObjetoNoEncontrado, configuracion_s3
from app.infra.bd import normalizar_url_bd

# ------------------------------------------------------------------ Neon


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        # La cadena tal como la copia Neon
        (
            "postgresql://usuario:clave@ep-abc-123.us-east-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://usuario:clave@ep-abc-123.us-east-2.aws.neon.tech/neondb"
            "?ssl=require",
        ),
        (
            "postgres://u:c@host:5432/db?sslmode=verify-full",
            "postgresql+asyncpg://u:c@host:5432/db?ssl=verify-full",
        ),
        # Ya en el formato de asyncpg: igual
        (
            "postgresql+asyncpg://u:c@host/db?ssl=require",
            "postgresql+asyncpg://u:c@host/db?ssl=require",
        ),
        # Sin parámetros (docker compose local)
        (
            "postgresql+asyncpg://storydraw:storydraw@db:5432/storydraw",
            "postgresql+asyncpg://storydraw:storydraw@db:5432/storydraw",
        ),
        ("sqlite+aiosqlite:///./prueba.db", "sqlite+aiosqlite:///./prueba.db"),
    ],
)
def test_la_url_de_la_base_de_datos_queda_lista_para_asyncpg(entrada, esperada):
    assert normalizar_url_bd(entrada) == esperada


def test_la_clave_con_caracteres_especiales_sobrevive():
    url = normalizar_url_bd("postgresql://u:p%40ss%2Fw@host/db?sslmode=require")
    assert url == "postgresql+asyncpg://u:p%40ss%2Fw@host/db?ssl=require"


# ------------------------------------------------------------------ configuración


RAIZ = Path(__file__).resolve().parents[2]
BLUEPRINT = yaml.safe_load((RAIZ / "render.yaml").read_text(encoding="utf-8"))
SERVICIO = BLUEPRINT["services"][0]
SECRETOS = {
    "DATABASE_URL",
    "JWT_SECRETO",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "OPENAI_API_KEY",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "ADMIN_EMAILS",
}


def _fijas_del_blueprint() -> dict[str, str]:
    return {v["key"]: str(v["value"]) for v in SERVICIO["envVars"] if "value" in v}


def _produccion(**cambios) -> Settings:
    """La configuración de Render: las variables fijas del Blueprint más secretos de mentira."""
    datos = {k.lower(): v for k, v in _fijas_del_blueprint().items()}
    datos.update(
        database_url="postgresql://u:***@ep-x.neon.tech/neondb?sslmode=require&channel_binding=require",
        url_publica="https://storydraw-api.onrender.com",
        cors_origenes="https://storydraw-api.onrender.com,https://josuehmz.github.io",
        jwt_secreto="s" * 48,
        openai_api_key="clave-de-prueba",
        cloudflare_account_id="cuenta",
        cloudflare_api_token="token-de-prueba",
        s3_access_key="HFAK-de-prueba",
        s3_secret_key="secreto-de-prueba",
    )
    datos.update(cambios)
    return Settings(_env_file=None, **datos)


def test_la_configuracion_de_render_es_valida_sin_voz_ni_correo_ni_rembg():
    s = _produccion()
    assert s.entorno == "produccion"
    assert s.proveedor_voz == "ninguno"
    assert (s.proveedor_correo, s.verificar_correo) == ("ninguno", False)
    assert s.recorte == "umbral"
    assert s.lista_cors == ["https://storydraw-api.onrender.com", "https://josuehmz.github.io"]
    assert (s.s3_endpoint_url, s.s3_bucket) == ("https://s3.hf.co/Josuehmz", "StoryDraw")
    assert (s.s3_estilo_direccion, s.s3_checksum, s.s3_cifrado_sse) == (
        "path",
        "when_required",
        False,
    )


# ------------------------------------------------------------------ Render y la imagen


def test_el_blueprint_es_un_web_service_docker_gratis_con_salud():
    assert len(BLUEPRINT["services"]) == 1
    assert SERVICIO["type"] == "web" and SERVICIO["runtime"] == "docker"
    assert SERVICIO["plan"] == "free"
    assert SERVICIO["rootDir"] == "backend"
    assert SERVICIO["healthCheckPath"] == "/salud"
    # dockerfilePath y dockerContext se cuentan desde la raíz del repo, no desde rootDir
    assert (RAIZ / SERVICIO["dockerfilePath"]).resolve() == RAIZ / "backend" / "Dockerfile"
    assert (RAIZ / SERVICIO["dockerContext"]).resolve() == RAIZ / "backend"


def test_el_blueprint_no_lleva_secretos_y_los_pide_en_el_panel():
    variables = {v["key"]: v for v in SERVICIO["envVars"]}
    for clave in SECRETOS:
        assert variables[clave] == {"key": clave, "sync": False}, clave
    # Ningún valor fijo se parece a una clave
    for clave, valor in _fijas_del_blueprint().items():
        assert clave not in SECRETOS
        assert not any(p in clave for p in ("TOKEN", "KEY", "SECRET", "CONTRASENA")), clave
        assert len(valor) < 40, clave
    assert "PORT" not in variables  # lo pone Render


def test_la_imagen_de_produccion_va_sin_rembg():
    backend = RAIZ / "backend"
    assert "rembg" not in (backend / "requirements.txt").read_text(encoding="utf-8")
    assert "rembg[cpu]==" in (backend / "requirements-rembg.txt").read_text(encoding="utf-8")
    dockerfile = (backend / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG CON_REMBG=0" in dockerfile
    compose = yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["services"]["api"]["build"]["args"]["CON_REMBG"] == "1"


def test_con_recorte_por_umbral_arrancar_no_importa_rembg():
    """En un proceso nuevo: construir la app y recortar un dibujo no carga rembg ni onnxruntime."""
    codigo = textwrap.dedent(
        """
        import io, sys
        from PIL import Image
        from app.config import Settings
        from app.contenedor import construir
        from app.main import create_app
        s = Settings(_env_file=None, jwt_secreto="s" * 48, almacen="memoria", recorte="umbral",
            **{f"proveedor_{c}": "falso" for c in ("vision", "texto", "moderacion", "imagen",
               "correo")})
        c = construir(s)
        create_app(s, c)
        img = Image.new("RGB", (64, 64), "white")
        img.paste((0, 0, 0), (10, 10, 40, 40))
        b = io.BytesIO(); img.save(b, format="PNG")
        assert c.orquestador.compositor.recortar(b.getvalue())
        print(sorted(m for m in sys.modules if m.split(".")[0] in ("rembg", "onnxruntime")))
        """
    )
    r = subprocess.run(  # noqa: S603 (código fijo de la prueba)
        [sys.executable, "-c", codigo],
        cwd=RAIZ / "backend",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "[]"


def test_por_defecto_el_s3_se_comporta_como_antes():
    s = Settings(
        _env_file=None,
        jwt_secreto="s" * 48,
        **{f"proveedor_{c}": "falso" for c in ("vision", "texto", "moderacion", "imagen")},
        proveedor_correo="falso",
        almacen="memoria",
    )
    assert (s.s3_estilo_direccion, s.s3_checksum, s.s3_cifrado_sse) == (
        "path",
        "when_supported",
        True,
    )


def test_la_configuracion_de_botocore_sale_de_los_ajustes():
    hf = configuracion_s3("us-east-1", "path", "when_required")
    assert hf.s3 == {"addressing_style": "path"}
    assert hf.request_checksum_calculation == "when_required"
    assert hf.response_checksum_validation == "when_required"
    assert hf.region_name == "us-east-1"
    assert configuracion_s3("us-east-1").request_checksum_calculation == "when_supported"


# ------------------------------------------------------------------ peticiones S3 (sin red)


class _CuerpoVacio:
    def stream(self, *_args, **_kwargs):
        return iter([b""])


def _capturar(almacen: AlmacenS3) -> list:
    """Intercepta las peticiones HTTP de botocore y responde 200 vacío."""
    peticiones: list = []

    def antes_de_enviar(request, **_):
        peticiones.append(request)
        return AWSResponse(request.url, 200, {}, _CuerpoVacio())

    almacen._s3.meta.events.register("before-send.s3", antes_de_enviar)
    return peticiones


def _hf(**cambios) -> AlmacenS3:
    datos = dict(
        bucket="storydraw-imagenes",
        access_key="HFAK-de-prueba",
        secret_key="secreto",
        region="us-east-1",
        endpoint_url="https://s3.hf.co/josuehmz",
        cifrado_sse=False,
        estilo_direccion="path",
        checksum="when_required",
    )
    datos.update(cambios)
    return AlmacenS3(**datos)


def test_con_hugging_face_la_subida_va_por_ruta_sin_sumas_ni_cifrado():
    almacen = _hf()
    peticiones = _capturar(almacen)
    asyncio.run(almacen.guardar("cuentos/c1/paginas/1.png", b"png", "image/png"))

    peticion = peticiones[-1]
    assert peticion.method == "PUT"
    assert peticion.url == ("https://s3.hf.co/josuehmz/storydraw-imagenes/cuentos/c1/paginas/1.png")
    cabeceras = {k.lower() for k in peticion.headers}
    assert not any(c.startswith("x-amz-checksum") for c in cabeceras)
    assert "x-amz-sdk-checksum-algorithm" not in cabeceras
    assert "x-amz-server-side-encryption" not in cabeceras
    assert "x-amz-acl" not in cabeceras  # nada público


def test_por_defecto_boto3_manda_sumas_y_cifrado_que_el_gateway_no_entiende():
    """Contraprueba: sin las opciones nuevas, la misma subida sí lleva esas cabeceras."""
    almacen = _hf(cifrado_sse=True, checksum="when_supported")
    peticiones = _capturar(almacen)
    asyncio.run(almacen.guardar("cuentos/c1/paginas/1.png", b"png", "image/png"))
    cabeceras = {k.lower() for k in peticiones[-1].headers}
    assert any(c.startswith("x-amz-checksum") for c in cabeceras) or (
        "x-amz-sdk-checksum-algorithm" in cabeceras
    )
    assert "x-amz-server-side-encryption" in cabeceras


def test_si_no_hay_borrado_por_lotes_se_borra_uno_por_uno():
    almacen = _hf()
    with Stubber(almacen._s3) as stub:
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "cuentos/c1/a.png"}, {"Key": "cuentos/c1/b.png"}]},
            {"Bucket": "storydraw-imagenes", "Prefix": "cuentos/c1/"},
        )
        stub.add_client_error("delete_objects", service_error_code="NotImplemented")
        for clave in ("cuentos/c1/a.png", "cuentos/c1/b.png"):
            stub.add_response("delete_object", {}, {"Bucket": "storydraw-imagenes", "Key": clave})
        assert asyncio.run(almacen.borrar_prefijo("cuentos/c1/")) == 2
        stub.assert_no_pending_responses()


def test_otros_errores_del_borrado_no_se_esconden():
    almacen = _hf()
    with Stubber(almacen._s3) as stub:
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "cuentos/c1/a.png"}]},
            {"Bucket": "storydraw-imagenes", "Prefix": "cuentos/c1/"},
        )
        stub.add_client_error("delete_objects", service_error_code="AccessDenied")
        with pytest.raises(ClientError):
            asyncio.run(almacen.borrar_prefijo("cuentos/c1/"))


# ------------------------------------------------------------------ MinIO real (opcional)

MINIO = os.environ.get("STORYDRAW_MINIO_URL")


@pytest.mark.skipif(not MINIO, reason="define STORYDRAW_MINIO_URL para probar contra MinIO")
@pytest.mark.parametrize(
    "opciones",
    [
        {"cifrado_sse": False, "estilo_direccion": "path", "checksum": "when_required"},
        {"cifrado_sse": False, "estilo_direccion": "path", "checksum": "when_supported"},
    ],
    ids=["como-hugging-face", "como-antes"],
)
def test_minio_guarda_lee_y_borra_con_las_opciones(opciones):
    almacen = AlmacenS3(
        bucket=f"prueba-{uuid.uuid4().hex[:8]}",
        access_key=os.environ["STORYDRAW_MINIO_USUARIO"],
        secret_key=os.environ["STORYDRAW_MINIO_CLAVE"],
        region="us-east-1",
        endpoint_url=MINIO,
        **opciones,
    )

    async def flujo() -> None:
        await almacen.asegurar_bucket()
        await almacen.guardar("cuentos/c1/paginas/1.png", b"\x89PNG-1", "image/png")
        await almacen.guardar("cuentos/c1/paginas/2.png", b"\x89PNG-2", "image/png")
        await almacen.guardar("cuentos/c2/paginas/1.png", b"\x89PNG-otro", "image/png")
        assert await almacen.leer("cuentos/c1/paginas/2.png") == b"\x89PNG-2"
        assert await almacen.borrar_prefijo("cuentos/c1/") == 2
        with pytest.raises(ObjetoNoEncontrado):
            await almacen.leer("cuentos/c1/paginas/1.png")
        assert await almacen.leer("cuentos/c2/paginas/1.png") == b"\x89PNG-otro"
        assert await almacen.borrar_prefijo("cuentos/") == 1

    asyncio.run(flujo())
