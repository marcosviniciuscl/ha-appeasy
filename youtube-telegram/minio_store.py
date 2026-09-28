# -*- coding: utf-8 -*-
"""Integração com o MinIO (S3) para arquivos que passam do limite do Telegram.

Usa boto3 (puro Python) e URLs pré-assinadas, então o bucket pode ficar privado.
"""
from __future__ import annotations

import logging
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

LOG = logging.getLogger("youtube-telegram.minio")


class MinioStore:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        endpoint = (cfg.minio_endpoint or "").strip()
        if not endpoint.startswith(("http://", "https://")):
            endpoint = ("https://" if cfg.minio_secure else "http://") + endpoint
        self.endpoint = endpoint.rstrip("/")
        self.bucket = cfg.minio_bucket
        self.cliente = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=cfg.minio_access,
            aws_secret_access_key=cfg.minio_secret,
            region_name=cfg.minio_regiao or "us-east-1",
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=10,
                read_timeout=120,
            ),
        )

    # ------------------------------------------------------------------ bucket
    def garantir_bucket(self) -> None:
        try:
            self.cliente.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            codigo = str(e.response.get("Error", {}).get("Code", ""))
            if codigo in ("404", "NoSuchBucket", "NotFound"):
                self.cliente.create_bucket(Bucket=self.bucket)
                LOG.info("Bucket '%s' criado no MinIO.", self.bucket)
            else:
                raise

    # ----------------------------------------------------------------- upload
    def enviar(self, caminho: Path, objeto: str) -> None:
        tipo = mimetypes.guess_type(str(caminho))[0] or "application/octet-stream"
        self.cliente.upload_file(
            str(caminho), self.bucket, objeto,
            ExtraArgs={"ContentType": tipo},
        )
        LOG.info("Enviado para o MinIO: %s (%d bytes)", objeto, caminho.stat().st_size)

    # ------------------------------------------------------------------- link
    def url_temporaria(self, objeto: str) -> str:
        return self.cliente.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": objeto},
            ExpiresIn=int(self.cfg.minio_expira_min) * 60,
        )

    # --------------------------------------------------------------- remoção
    def apagar(self, objeto: str) -> None:
        try:
            self.cliente.delete_object(Bucket=self.bucket, Key=objeto)
            LOG.info("Apagado do MinIO: %s", objeto)
        except Exception as e:  # noqa: BLE001 — não pode derrubar o bot
            LOG.warning("Falha ao apagar '%s' do MinIO: %s", objeto, e)

    def limpar_antigos(self, prefixo: str, idade_min: int) -> int:
        """Remove objetos do prefixo mais velhos que `idade_min` minutos."""
        limite = datetime.now(timezone.utc) - timedelta(minutes=max(int(idade_min), 1))
        removidos = 0
        try:
            paginador = self.cliente.get_paginator("list_objects_v2")
            for pagina in paginador.paginate(Bucket=self.bucket, Prefix=prefixo):
                for obj in pagina.get("Contents", []):
                    quando = obj.get("LastModified")
                    if quando and quando < limite:
                        self.apagar(obj["Key"])
                        removidos += 1
        except Exception as e:  # noqa: BLE001
            LOG.warning("Falha na limpeza de objetos antigos do MinIO: %s", e)
        return removidos
