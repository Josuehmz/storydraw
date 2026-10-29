"""Dibujos y cuentos: identificación asistida, creación, consulta, medios y borrado."""

import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from app.api import limites
from app.api.dependencias import contenedor, repositorio, tutor_con_consentimiento
from app.api.esquemas import CuentoCreado, CuentoSalida, HipotesisSalida, IdentificacionSalida
from app.contenedor import Contenedor
from app.dominio.composicion import DibujoInvalido, abrir_dibujo
from app.infra.adaptadores.almacen import ObjetoNoEncontrado
from app.infra.orm import Tutor
from app.infra.repositorio import Repositorio
from app.servicios import a_salida, borrar_cuentos, procesar_cuento

router = APIRouter(prefix="/v1", tags=["cuentos"])


async def _leer_dibujo(c: Contenedor, archivo: UploadFile) -> bytes:
    """Lee el dibujo en memoria, con tope de tamaño. Nunca toca el disco."""
    maximo = c.settings.max_dibujo_bytes
    datos = await archivo.read(maximo + 1)
    if len(datos) > maximo:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "dibujo_demasiado_grande")
    try:
        return abrir_dibujo(datos)
    except DibujoInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "dibujo_invalido") from exc


@router.post("/dibujos/identificar", response_model=IdentificacionSalida)
@limites.limiter.limit(limites.limite_identificar)
@limites.limiter.limit(limites.limite_identificar, key_func=limites.clave_cuenta)
async def identificar(
    request: Request,
    dibujo: UploadFile = File(...),
    tutor: Tutor = Depends(tutor_con_consentimiento),
    c: Contenedor = Depends(contenedor),
) -> IdentificacionSalida:
    """Paso 1 a la vista del niño: hipótesis con su confianza. Si la visión cae,
    `disponible` es false y la app muestra solo el campo libre."""
    png = await _leer_dibujo(c, dibujo)
    resultado = await c.orquestador.identificar(png)
    return IdentificacionSalida(
        disponible=resultado.disponible,
        hipotesis=[
            HipotesisSalida(etiqueta=h.etiqueta, confianza=h.confianza) for h in resultado.hipotesis
        ],
    )


@router.post("/cuentos", response_model=CuentoCreado, status_code=status.HTTP_202_ACCEPTED)
@limites.limiter.limit(limites.limite_cuentos_ip)
@limites.limiter.limit(limites.limite_cuentos_cuenta, key_func=limites.clave_cuenta)
async def crear_cuento(
    request: Request,
    tareas: BackgroundTasks,
    dibujo: UploadFile = File(...),
    perfil_id: uuid.UUID = Form(...),
    personaje: str | None = Form(None, max_length=120),
    nombre: str | None = Form(None, max_length=40),
    tutor: Tutor = Depends(tutor_con_consentimiento),
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> CuentoCreado:
    """Encola el cuento y responde al instante; la app consulta el estado mientras
    muestra el momento mágico."""
    perfil = await repo.perfil_de(tutor.id, perfil_id)
    if perfil is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "perfil_inexistente")
    png = await _leer_dibujo(c, dibujo)
    cuento = await repo.crear_cuento(tutor.id, perfil.id)
    tareas.add_task(procesar_cuento, c, cuento.id, png, personaje, perfil.edad, nombre)
    return CuentoCreado(id=cuento.id, estado=cuento.estado)


async def _cuento_o_404(repo: Repositorio, tutor: Tutor, cuento_id: uuid.UUID):
    cuento = await repo.cuento_de(tutor.id, cuento_id)
    if cuento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cuento_inexistente")
    return cuento


@router.get("/cuentos/{cuento_id}", response_model=CuentoSalida)
async def consultar(
    cuento_id: uuid.UUID,
    tutor: Tutor = Depends(tutor_con_consentimiento),
    repo: Repositorio = Depends(repositorio),
) -> CuentoSalida:
    return a_salida(await _cuento_o_404(repo, tutor, cuento_id))


@router.get("/cuentos/{cuento_id}/paginas/{numero}/imagen", response_class=Response)
async def imagen(
    cuento_id: uuid.UUID,
    numero: int,
    tutor: Tutor = Depends(tutor_con_consentimiento),
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> Response:
    cuento = await _cuento_o_404(repo, tutor, cuento_id)
    pagina = next((p for p in cuento.paginas if p.numero == numero), None)
    if cuento.estado != "listo" or pagina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pagina_inexistente")
    try:
        datos = await c.almacen.leer(pagina.imagen_clave)
    except ObjetoNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "objeto_inexistente") from exc
    return Response(
        datos, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.delete("/cuentos/{cuento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar(
    cuento_id: uuid.UUID,
    tutor: Tutor = Depends(tutor_con_consentimiento),
    c: Contenedor = Depends(contenedor),
    repo: Repositorio = Depends(repositorio),
) -> Response:
    """Borrado a petición: filas, páginas, imágenes y el texto del registro de moderación."""
    cuento = await _cuento_o_404(repo, tutor, cuento_id)
    await borrar_cuentos(c, [cuento.id])
    await repo.borrar_cuento(cuento.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
