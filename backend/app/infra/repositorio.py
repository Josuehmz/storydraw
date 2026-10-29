"""Repositorio SQLAlchemy: todo el acceso a la base de datos pasa por aquí."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dominio.orquestador import ResultadoCuento
from app.infra.orm import (
    Consentimiento,
    Cuento,
    Pagina,
    Perfil,
    RegistroModeracion,
    Tutor,
    ahora,
)


class Repositorio:
    def __init__(self, sesion: AsyncSession):
        self.s = sesion

    # ------------------------------------------------------------ cuentas

    async def tutor_por_email(self, email: str) -> Tutor | None:
        return await self.s.scalar(select(Tutor).where(Tutor.email == email.lower()))

    async def tutor_por_id(self, tutor_id: uuid.UUID) -> Tutor | None:
        return await self.s.get(Tutor, tutor_id)

    async def crear_tutor_con_consentimiento(
        self, email: str, hash_contrasena: str, rol: str, version: str
    ) -> Tutor:
        """Cuenta y consentimiento se escriben en la misma transacción."""
        tutor = Tutor(email=email.lower(), hash_contrasena=hash_contrasena, rol=rol)
        tutor.consentimientos.append(Consentimiento(version=version))
        self.s.add(tutor)
        await self.s.commit()
        return tutor

    async def tiene_consentimiento(self, tutor_id: uuid.UUID) -> bool:
        total = await self.s.scalar(
            select(func.count())
            .select_from(Consentimiento)
            .where(Consentimiento.tutor_id == tutor_id)
        )
        return bool(total)

    async def marcar_verificado(self, tutor_id: uuid.UUID) -> bool:
        res = await self.s.execute(
            update(Tutor).where(Tutor.id == tutor_id).values(verificado=True)
        )
        await self.s.commit()
        return res.rowcount > 0

    async def borrar_tutor(self, tutor_id: uuid.UUID) -> None:
        await self._anonimizar_moderacion(select(Cuento.id).where(Cuento.tutor_id == tutor_id))
        await self.s.execute(delete(Tutor).where(Tutor.id == tutor_id))
        await self.s.commit()

    # ------------------------------------------------------------ perfiles

    async def crear_perfil(self, tutor_id: uuid.UUID, apodo: str, edad: int) -> Perfil:
        perfil = Perfil(tutor_id=tutor_id, apodo=apodo, edad=edad)
        self.s.add(perfil)
        await self.s.commit()
        return perfil

    async def perfiles_de(self, tutor_id: uuid.UUID) -> list[Perfil]:
        res = await self.s.scalars(
            select(Perfil).where(Perfil.tutor_id == tutor_id).order_by(Perfil.creado_en)
        )
        return list(res)

    async def perfil_de(self, tutor_id: uuid.UUID, perfil_id: uuid.UUID) -> Perfil | None:
        return await self.s.scalar(
            select(Perfil).where(Perfil.id == perfil_id, Perfil.tutor_id == tutor_id)
        )

    async def borrar_perfil(self, perfil_id: uuid.UUID) -> None:
        await self._anonimizar_moderacion(select(Cuento.id).where(Cuento.perfil_id == perfil_id))
        await self.s.execute(delete(Perfil).where(Perfil.id == perfil_id))
        await self.s.commit()

    # ------------------------------------------------------------ cuentos

    async def crear_cuento(self, tutor_id: uuid.UUID, perfil_id: uuid.UUID) -> Cuento:
        cuento = Cuento(tutor_id=tutor_id, perfil_id=perfil_id, estado="en_proceso")
        self.s.add(cuento)
        await self.s.commit()
        return cuento

    async def cuento_de(self, tutor_id: uuid.UUID, cuento_id: uuid.UUID) -> Cuento | None:
        return await self.s.scalar(
            select(Cuento).where(Cuento.id == cuento_id, Cuento.tutor_id == tutor_id)
        )

    async def cuentos_de_perfil(self, perfil_id: uuid.UUID) -> list[Cuento]:
        res = await self.s.scalars(
            select(Cuento)
            .where(Cuento.perfil_id == perfil_id, Cuento.estado == "listo")
            .order_by(Cuento.creado_en.desc())
        )
        return list(res)

    async def ids_cuentos(self, *, perfil_id=None, tutor_id=None) -> list[uuid.UUID]:
        consulta = select(Cuento.id)
        if perfil_id is not None:
            consulta = consulta.where(Cuento.perfil_id == perfil_id)
        if tutor_id is not None:
            consulta = consulta.where(Cuento.tutor_id == tutor_id)
        return list(await self.s.scalars(consulta))

    async def guardar_resultado(self, cuento_id: uuid.UUID, r: ResultadoCuento) -> None:
        cuento = await self.s.get(Cuento, cuento_id)
        if cuento is None:  # se borró mientras se generaba
            return
        cuento.estado = r.estado
        cuento.titulo = r.titulo
        cuento.personaje = r.personaje
        cuento.avisos = list(r.avisos)
        cuento.pasos = [p.como_dict() for p in r.pasos]
        cuento.latencia_ms = r.latencia_ms
        cuento.costo_usd = r.costo_usd
        cuento.terminado_en = ahora()
        for p in r.paginas:
            self.s.add(
                Pagina(
                    cuento_id=cuento_id,
                    numero=p.numero,
                    texto=p.texto,
                    imagen_clave=p.imagen_clave,
                    audio_clave=p.audio_clave,
                )
            )
        for rechazo in r.rechazos:
            self.s.add(
                RegistroModeracion(
                    cuento_id=cuento_id,
                    origen=rechazo.origen,
                    texto=rechazo.texto,
                    categorias=rechazo.categorias,
                )
            )
        await self.s.commit()

    async def borrar_cuento(self, cuento_id: uuid.UUID) -> None:
        await self._anonimizar_moderacion(select(Cuento.id).where(Cuento.id == cuento_id))
        await self.s.execute(delete(Cuento).where(Cuento.id == cuento_id))
        await self.s.commit()

    async def _anonimizar_moderacion(self, ids_cuentos) -> None:
        """El registro de moderación se conserva para mejorar el filtro, pero sin texto."""
        await self.s.execute(
            update(RegistroModeracion)
            .where(RegistroModeracion.cuento_id.in_(ids_cuentos))
            .values(texto=None, cuento_id=None)
        )

    # ------------------------------------------------------------ operación

    async def cuentos_recientes(self, limite: int) -> list[Cuento]:
        res = await self.s.scalars(select(Cuento).order_by(Cuento.creado_en.desc()).limit(limite))
        return list(res)

    async def cuentos_desde(self, desde: datetime | None) -> list[Cuento]:
        consulta = select(Cuento).where(Cuento.estado != "en_proceso")
        if desde is not None:
            consulta = consulta.where(Cuento.creado_en >= desde)
        return list(await self.s.scalars(consulta))

    async def cola_moderacion(self, solo_pendientes: bool) -> list[RegistroModeracion]:
        consulta = select(RegistroModeracion).order_by(RegistroModeracion.creado_en.desc())
        if solo_pendientes:
            consulta = consulta.where(RegistroModeracion.revisado.is_(False))
        return list(await self.s.scalars(consulta.limit(200)))

    async def marcar_revisado(self, registro_id: uuid.UUID) -> bool:
        res = await self.s.execute(
            update(RegistroModeracion)
            .where(RegistroModeracion.id == registro_id)
            .values(revisado=True)
        )
        await self.s.commit()
        return res.rowcount > 0
