from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from holocron.platform.settings import Settings


class ObjectStorageClient:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.object_storage_bucket
        self._public_url_base = settings.object_storage_public_url_base.strip()
        session_kwargs: dict[str, Any] = {
            "region_name": settings.object_storage_region,
            "aws_access_key_id": settings.object_storage_access_key_id,
            "aws_secret_access_key": settings.object_storage_secret_access_key,
        }
        session = boto3.session.Session(**session_kwargs)
        config = Config(
            s3={"addressing_style": "path" if settings.object_storage_use_path_style else "auto"}
        )
        self._client = session.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint_url or None,
            config=config,
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def upload_file(self, *, path: str | Path, key: str, content_type: str | None = None) -> None:
        extra_args = {"ContentType": content_type} if content_type else None
        self._client.upload_file(str(path), self._bucket, key, ExtraArgs=extra_args or {})

    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(payload, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )

    def get_json(self, *, key: str) -> dict[str, Any] | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        payload = json.loads(response["Body"].read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Object-storage JSON object at key={key} must be a JSON object")
        return payload

    def put_bytes(self, *, key: str, payload: bytes, content_type: str | None = None) -> None:
        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        self._client.put_object(Bucket=self._bucket, Key=key, Body=payload, **extra_args)

    def list_keys(self, *, prefix: str) -> list[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key")
                if isinstance(key, str):
                    keys.append(key)
        return keys

    def read_bytes(self, *, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def read_text(self, *, key: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(key=key).decode(encoding)

    def object_exists(self, *, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def public_url(self, *, key: str) -> str | None:
        if not self._public_url_base:
            return None
        return f"{self._public_url_base.rstrip('/')}/{key}"

    def download_file(self, *, key: str, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self._bucket, key, str(destination))
