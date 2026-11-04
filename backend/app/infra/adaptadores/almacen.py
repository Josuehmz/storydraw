"""Almacenes de objetos: S3 compatible (AWS, MinIO, R2, Hugging Face...) y uno en memoria.

Los objetos nunca son públicos: el bucket es privado y la API sirve cada imagen solo a su
dueño (no hay URLs firmadas ni enlaces directos al almacén).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.dominio.puertos import IAlmacen

log = logging.getLogger(__name__)

# Errores con los que un S3 compatible dice que no implementa el borrado por lotes.
_SIN_LOTES = {"NotImplemented", "NotSupported", "MethodNotAllowed", "InvalidRequest"}


class ObjetoNoEncontrado(KeyError):
    pass


def configuracion_s3(
    region: str,
    estilo_direccion: Literal["path", "virtual", "auto"] = "path",
    checksum: Literal["when_supported", "when_required"] = "when_supported",
) -> Config:
    """La configuración de botocore sale de los ajustes (`S3_ESTILO_DIRECCION`, `S3_CHECKSUM`)."""
    return Config(
        region_name=region,
        signature_version="s3v4",
        s3={"addressing_style": estilo_direccion},
        request_checksum_calculation=checksum,
        response_checksum_validation=checksum,
    )


class AlmacenS3(IAlmacen):
    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        endpoint_url: str | None = None,
        cifrado_sse: bool = True,
        estilo_direccion: Literal["path", "virtual", "auto"] = "path",
        checksum: Literal["when_supported", "when_required"] = "when_supported",
    ):
        self._bucket = bucket
        self._por_lotes = True
        # Cifrado en reposo SSE-S3. MinIO sin KMS y Hugging Face no lo admiten: allí se apaga.
        self._extra = {"ServerSideEncryption": "AES256"} if cifrado_sse else {}
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=configuracion_s3(region, estilo_direccion, checksum),
        )

    async def asegurar_bucket(self) -> None:
        def _crear() -> None:
            try:
                self._s3.head_bucket(Bucket=self._bucket)
            except ClientError:
                self._s3.create_bucket(Bucket=self._bucket)

        await asyncio.to_thread(_crear)

    async def guardar(self, clave: str, datos: bytes, tipo: str) -> None:
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self._bucket,
            Key=clave,
            Body=datos,
            ContentType=tipo,
            **self._extra,
        )

    async def leer(self, clave: str) -> bytes:
        def _leer() -> bytes:
            try:
                return self._s3.get_object(Bucket=self._bucket, Key=clave)["Body"].read()
            except ClientError as exc:
                raise ObjetoNoEncontrado(clave) from exc

        return await asyncio.to_thread(_leer)

    async def borrar_prefijo(self, prefijo: str) -> int:
        def _borrar() -> int:
            total = 0
            paginador = self._s3.get_paginator("list_objects_v2")
            for pagina in paginador.paginate(Bucket=self._bucket, Prefix=prefijo):
                claves = [o["Key"] for o in pagina.get("Contents", [])]
                if claves:
                    self._borrar_claves(claves)
                    total += len(claves)
            return total

        return await asyncio.to_thread(_borrar)

    def _borrar_claves(self, claves: list[str]) -> None:
        """Borra por lotes; si el S3 compatible no implementa DeleteObjects, uno por uno."""
        if self._por_lotes:
            try:
                respuesta = self._s3.delete_objects(
                    Bucket=self._bucket, Delete={"Objects": [{"Key": c} for c in claves]}
                )
                fallidas = [e["Key"] for e in respuesta.get("Errors", [])]
                if not fallidas:
                    return
                claves = fallidas
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in _SIN_LOTES:
                    raise
                log.warning("El almacén no admite DeleteObjects: se borra objeto por objeto")
                self._por_lotes = False
        for clave in claves:
            self._s3.delete_object(Bucket=self._bucket, Key=clave)


class AlmacenMemoria(IAlmacen):
    def __init__(self) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}

    async def guardar(self, clave: str, datos: bytes, tipo: str) -> None:
        self.objetos[clave] = (datos, tipo)

    async def leer(self, clave: str) -> bytes:
        try:
            return self.objetos[clave][0]
        except KeyError as exc:
            raise ObjetoNoEncontrado(clave) from exc

    async def borrar_prefijo(self, prefijo: str) -> int:
        claves = [c for c in self.objetos if c.startswith(prefijo)]
        for c in claves:
            del self.objetos[c]
        return len(claves)
