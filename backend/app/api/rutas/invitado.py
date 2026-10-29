"""Modo invitado: SOLO PRUEBAS LOCALES.

Estas rutas existen solo con `PERMITIR_INVITADOS=true`, que la configuración rechaza en
producción. El invitado recibe un token corto sin cuenta ni consentimiento, genera
cuentos y se los lleva enteros a su dispositivo: el servidor no los guarda en la base de
datos y los olvida al entregarlos. La moderación es la misma que con cuenta.
"""

import base64
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api import limites
from app.api.dependencias import contenedor
from app.api.esquemas import (
    CuentoCreado,
    CuentoInvitadoSalida,
    HipotesisSalida,
    IdentificacionSalida,
    PaginaInvitado,
    TokenSalida,
)
from app.api.rutas.cuentos import _leer_dibujo
from app.contenedor import Contenedor
from app.infra.seguridad import TokenInvalido
from app.servicios import procesar_cuento_invitado

router = APIRouter(prefix="/v1/invitado", tags=["invitado (solo local)"])

_bearer = HTTPBearer(auto_error=False)


def invitado_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    c: Contenedor = Depends(contenedor),
) -> str:
    no_autorizado = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "no_autenticado", headers={"WWW-Authenticate": "Bearer"}
    )
    if credenciales is None:
        raise no_autorizado
    try:
        return c.tokens.leer(credenciales.credentials, "invitado")["sub"]
    except TokenInvalido as exc:
        raise no_autorizado from exc


@router.post("", response_model=TokenSalida, status_code=status.HTTP_201_CREATED)
@limites.limiter.limit(limites.limite_auth)
async def entrar(request: Request, c: Contenedor = Depends(contenedor)) -> TokenSalida:
    """Token de invitado: sin correo, sin contraseña y sin consentimiento."""
    token, expira = c.tokens.emitir(uuid.uuid4(), "invitado", "invitado")
    return TokenSalida(access_token=token, expira_en=expira, rol="invitado")


@router.post("/dibujos/identificar", response_model=IdentificacionSalida)
@limites.limiter.limit(limites.limite_identificar)
async def identificar(
    request: Request,
    dibujo: UploadFile = File(...),
    invitado: str = Depends(invitado_actual),
    c: Contenedor = Depends(contenedor),
) -> IdentificacionSalida:
    png = await _leer_dibujo(c, dibujo)
    resultado = await c.orquestador.identificar(png)
    return IdentificacionSalida(
        disponible=resultado.disponible,
        hipotesis=[
            HipotesisSalida(etiqueta=h.etiqueta, confianza=h.confianza) for h in resultado.hipotesis
        ],
    )


@router.post("/cuentos", response_model=CuentoCreado, status_code=status.HTTP_202_ACCEPTED)
@limites.limiter.limit(limites.limite_invitado_ip, key_func=limites.clave_invitado_ip)
async def crear_cuento(
    request: Request,
    tareas: BackgroundTasks,
    dibujo: UploadFile = File(...),
    edad: int = Form(..., ge=6, le=12),
    personaje: str | None = Form(None, max_length=120),
    nombre: str | None = Form(None, max_length=40),
    invitado: str = Depends(invitado_actual),
    c: Contenedor = Depends(contenedor),
) -> CuentoCreado:
    png = await _leer_dibujo(c, dibujo)
    trabajo = c.invitados.crear(invitado)
    tareas.add_task(procesar_cuento_invitado, c, trabajo.id, png, personaje, edad, nombre)
    return CuentoCreado(id=trabajo.id, estado="en_proceso")


@router.get("/cuentos/{cuento_id}", response_model=CuentoInvitadoSalida)
async def consultar(
    cuento_id: uuid.UUID,
    invitado: str = Depends(invitado_actual),
    c: Contenedor = Depends(contenedor),
) -> CuentoInvitadoSalida:
    """Mientras está en proceso solo da el estado. Al terminar entrega el cuento entero
    (texto e imágenes en base64) una sola vez y el servidor lo olvida."""
    trabajo = c.invitados.de(invitado, cuento_id)
    if trabajo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cuento_inexistente")
    if trabajo.resultado is None:
        return CuentoInvitadoSalida(id=trabajo.id, estado="en_proceso")
    r = trabajo.resultado
    c.invitados.olvidar(trabajo.id)
    if r.estado != "listo":
        return CuentoInvitadoSalida(id=trabajo.id, estado=r.estado, avisos=list(r.avisos))
    return CuentoInvitadoSalida(
        id=trabajo.id,
        estado="listo",
        titulo=r.titulo,
        personaje=r.personaje,
        avisos=list(r.avisos),
        paginas=[
            PaginaInvitado(
                numero=p.numero,
                texto=p.texto,
                imagen_png_base64=base64.b64encode(trabajo.imagenes[p.numero]).decode("ascii"),
            )
            for p in r.paginas
        ],
    )
