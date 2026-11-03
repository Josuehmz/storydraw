"""Cuentas: registro con consentimiento previo, verificación por correo y login JWT."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from app.api import limites
from app.api.dependencias import contenedor, repositorio, tutor_actual
from app.api.esquemas import LoginEntrada, RegistroEntrada, RegistroSalida, TokenSalida
from app.api.plantillas import (
    correo_verificacion,
    enlace_app,
    enlace_app_android,
    pagina_confirmada,
    pagina_error,
)
from app.contenedor import Contenedor
from app.infra.orm import Tutor
from app.infra.repositorio import Repositorio
from app.infra.seguridad import TokenInvalido
from app.servicios import borrar_cuentos

router = APIRouter(prefix="/v1/auth", tags=["cuentas"])
log = logging.getLogger(__name__)


def _rol_para(c: Contenedor, email: str) -> str:
    email = email.lower()
    if email in c.settings.lista_admin:
        return "admin"
    if email in c.settings.lista_contenido:
        return "contenido"
    return "tutor"


def _dominio_permitido(c: Contenedor, email: str) -> bool:
    permitidos = c.settings.lista_dominios_correo
    return not permitidos or email.rsplit("@", 1)[-1].lower() in permitidos


async def _enviar_verificacion(c: Contenedor, tutor: Tutor) -> bool:
    """Manda el correo de confirmación. Devuelve False (sin romper el registro) si no salió."""
    token, _ = c.tokens.emitir(tutor.id, "verificacion")
    enlace = f"{c.settings.url_publica.rstrip('/')}/v1/auth/verificar?token={token}"
    asunto, texto, html = correo_verificacion(enlace)
    try:
        await c.correo.enviar(tutor.email, asunto, texto, html)
    except Exception:
        log.exception("No se pudo enviar el correo de verificación a la cuenta %s", tutor.id)
        return False
    return True


@router.post("/registro", response_model=RegistroSalida, status_code=status.HTTP_201_CREATED)
@limites.limiter.limit(limites.limite_auth)
async def registrar(
    request: Request,
    datos: RegistroEntrada,
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> RegistroSalida:
    if not _dominio_permitido(c, datos.email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "dominio_no_permitido")
    if await repo.tutor_por_email(datos.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email_registrado")
    tutor = await repo.crear_tutor_con_consentimiento(
        datos.email,
        c.hasher.hashear(datos.contrasena),
        _rol_para(c, datos.email),
        c.settings.version_consentimiento,
    )
    enviado = await _enviar_verificacion(c, tutor)
    return RegistroSalida(
        id=tutor.id,
        email=tutor.email,
        verificado=tutor.verificado,
        version_consentimiento=c.settings.version_consentimiento,
        correo_enviado=enviado,
    )


@router.get("/verificar", response_model=None)
async def verificar(
    request: Request,
    token: str,
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> dict | HTMLResponse:
    """Confirma el correo. Un navegador (Accept: text/html) recibe una página que abre la app;
    cualquier otro cliente recibe JSON."""
    quiere_html = "text/html" in request.headers.get("accept", "")
    try:
        carga = c.tokens.leer(token, "verificacion")
        tutor_id = uuid.UUID(carga["sub"])
    except (TokenInvalido, ValueError) as exc:
        if quiere_html:
            return HTMLResponse(pagina_error(), status_code=status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "token_invalido") from exc
    if not await repo.marcar_verificado(tutor_id):
        if quiere_html:
            return HTMLResponse(pagina_error(), status_code=status.HTTP_404_NOT_FOUND)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cuenta_inexistente")
    if not quiere_html:
        return {"verificado": True}
    tutor = await repo.tutor_por_id(tutor_id)
    email = tutor.email if tutor else ""
    esquema = c.settings.app_esquema
    return HTMLResponse(
        pagina_confirmada(
            email,
            enlace_app(esquema, email),
            enlace_app_android(esquema, c.settings.app_paquete_android, email),
        )
    )


@router.post("/reenviar-verificacion", status_code=status.HTTP_202_ACCEPTED)
@limites.limiter.limit(limites.limite_auth)
async def reenviar(
    request: Request,
    datos: LoginEntrada,
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> dict:
    tutor = await repo.tutor_por_email(datos.email)
    if (
        tutor
        and not tutor.verificado
        and c.hasher.verificar(tutor.hash_contrasena, datos.contrasena)
    ):
        await _enviar_verificacion(c, tutor)
    return {"enviado": True}


@router.post("/login", response_model=TokenSalida)
@limites.limiter.limit(limites.limite_auth)
async def login(
    request: Request,
    datos: LoginEntrada,
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> TokenSalida:
    tutor = await repo.tutor_por_email(datos.email)
    if tutor is None or not c.hasher.verificar(tutor.hash_contrasena, datos.contrasena):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credenciales_invalidas")
    if not tutor.verificado:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "correo_sin_verificar")
    rol = _rol_para(c, tutor.email)
    if rol != tutor.rol:
        tutor.rol = rol
        await repo.s.commit()
    token, expira = c.tokens.emitir(tutor.id, "acceso", tutor.rol)
    return TokenSalida(access_token=token, expira_en=expira, rol=tutor.rol)


@router.delete("/cuenta", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_cuenta(
    tutor: Tutor = Depends(tutor_actual),
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> Response:
    """Borrado a petición de toda la cuenta: perfiles, cuentos, páginas e imágenes."""
    await borrar_cuentos(c, await repo.ids_cuentos(tutor_id=tutor.id))
    await repo.borrar_tutor(tutor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
