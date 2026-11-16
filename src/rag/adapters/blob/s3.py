"""S3-compatible private object storage using Boto3 managed transfers."""

from __future__ import annotations

import asyncio
from typing import BinaryIO

import boto3
from botocore.config import Config
from boto3.s3.transfer import TransferConfig


class S3BlobStore:
    """S3/R2-compatible storage with bounded multipart upload concurrency."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> None:
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                connect_timeout=3,
                read_timeout=20,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )
        self._transfer = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            multipart_chunksize=8 * 1024 * 1024,
            max_concurrency=2,
            use_threads=True,
        )

    async def put(self, key: str, source: BinaryIO) -> None:
        await asyncio.to_thread(
            self._client.upload_fileobj,
            source,
            self.bucket,
            key,
            ExtraArgs={"ContentType": "application/pdf", "ServerSideEncryption": "AES256"},
            Config=self._transfer,
        )

    async def download(self, key: str, destination: BinaryIO) -> None:
        await asyncio.to_thread(self._client.download_fileobj, self.bucket, key, destination)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)
