"""Almacenes de objetos: S3 compatible (AWS, MinIO, R2...) y uno en memoria para pruebas."""

from __future__ import annotations

import asyncio

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.dominio.puertos import IAlmacen


class ObjetoNoEncontrado(KeyError):
    pass


class AlmacenS3(IAlmacen):
    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        endpoint_url: str | None = None,
        cifrado_sse: bool = True,
    ):
        self._bucket = bucket
        # Cifrado en reposo SSE-S3. MinIO sin KMS no lo admite: en local se apaga.
        self._extra = {"ServerSideEncryption": "AES256"} if cifrado_sse else {}
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
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
                objetos = [{"Key": o["Key"]} for o in pagina.get("Contents", [])]
                if objetos:
                    self._s3.delete_objects(Bucket=self._bucket, Delete={"Objects": objetos})
                    total += len(objetos)
            return total

        return await asyncio.to_thread(_borrar)


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
