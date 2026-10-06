from __future__ import annotations

import argparse
import os
import shlex
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import clickhouse_connect
import psycopg
from botocore.config import Config


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


CORE_REQUIRED_ENV = (
    "DAGSTER_POSTGRES_URL",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "OBJECT_STORAGE_REGION",
    "OBJECT_STORAGE_BUCKET",
)

CLICKHOUSE_REQUIRED_ENV = (
    "CLICKHOUSE_HOST",
    "CLICKHOUSE_PORT",
    "CLICKHOUSE_USER",
    "CLICKHOUSE_PASSWORD",
    "CLICKHOUSE_DATABASE",
    "CLICKHOUSE_SECURE",
)

OPTIONAL_SOURCE_ENV = (
    "REELLY_EMAIL",
    "REELLY_PASSWORD",
    "PLATFORM_POSTGRES_URL",
    "NEWS_FEED_URLS",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Holocron VPS configuration.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file to validate. Defaults to .env.",
    )
    parser.add_argument(
        "--check-connections",
        action="store_true",
        help="Connect to remote Dagster Postgres, object storage, and ClickHouse.",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Validate only the services needed for raw extraction: Dagster Postgres and object storage.",
    )
    args = parser.parse_args(argv)

    env = {**os.environ, **_read_env_file(Path(args.env_file))}
    required_env = (
        CORE_REQUIRED_ENV if args.raw_only else CORE_REQUIRED_ENV + CLICKHOUSE_REQUIRED_ENV
    )
    results = [
        _check_required_env(env, required_env=required_env),
        _check_object_storage_provider(env),
        _check_object_storage_endpoint(env),
        _check_postgres_url(env),
        _check_boolean(env, "OBJECT_STORAGE_USE_PATH_STYLE", required=False),
        _check_optional_sources(env),
    ]
    if not args.raw_only:
        results.extend(
            [
                _check_clickhouse_port(env),
                _check_boolean(env, "CLICKHOUSE_SECURE"),
            ]
        )
    if args.check_connections:
        results.extend(
            [
                _check_postgres_connection(env),
                _check_object_storage_connection(env),
            ]
        )
        if not args.raw_only:
            results.append(_check_clickhouse_connection(env))

    for result in results:
        status = "ok" if result.ok else "fail"
        print(f"[{status}] {result.name}: {result.detail}")

    return 0 if all(result.ok for result in results) else 1


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise ValueError(f"Invalid env line {path}:{line_number}: expected KEY=value")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid env line {path}:{line_number}: missing key")
        values[key] = _parse_env_value(raw_value.strip())
    return values


def _parse_env_value(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = shlex.split(value, comments=False, posix=True)
    except ValueError:
        return value
    if len(parsed) == 1:
        return parsed[0]
    return value


def _check_required_env(env: Mapping[str, str], *, required_env: tuple[str, ...]) -> CheckResult:
    missing = [key for key in required_env if not env.get(key, "").strip()]
    if missing:
        return CheckResult(
            name="required env",
            ok=False,
            detail=f"missing required keys: {', '.join(missing)}",
        )
    return CheckResult(name="required env", ok=True, detail="all required keys are set")


def _check_postgres_url(env: Mapping[str, str]) -> CheckResult:
    url = env.get("DAGSTER_POSTGRES_URL", "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        return CheckResult(
            name="dagster postgres url",
            ok=False,
            detail="DAGSTER_POSTGRES_URL must start with postgresql:// or postgres://",
        )
    if not parsed.hostname or not parsed.path.strip("/"):
        return CheckResult(
            name="dagster postgres url",
            ok=False,
            detail="DAGSTER_POSTGRES_URL must include host and database name",
        )
    return CheckResult(name="dagster postgres url", ok=True, detail="URL shape is valid")


def _check_clickhouse_port(env: Mapping[str, str]) -> CheckResult:
    try:
        port = int(env.get("CLICKHOUSE_PORT", ""))
    except ValueError:
        return CheckResult(
            name="clickhouse port",
            ok=False,
            detail="CLICKHOUSE_PORT must be an integer",
        )
    if not 1 <= port <= 65535:
        return CheckResult(
            name="clickhouse port",
            ok=False,
            detail="CLICKHOUSE_PORT must be between 1 and 65535",
        )
    return CheckResult(name="clickhouse port", ok=True, detail=str(port))


def _check_boolean(env: Mapping[str, str], key: str, *, required: bool = True) -> CheckResult:
    raw_value = env.get(key, "").strip()
    if not raw_value and not required:
        return CheckResult(name=key, ok=True, detail="not set; using application default")
    if raw_value.lower() not in {"true", "false", "1", "0", "yes", "no"}:
        return CheckResult(name=key, ok=False, detail=f"{key} must be true or false")
    return CheckResult(name=key, ok=True, detail=raw_value)


def _object_storage_provider(env: Mapping[str, str]) -> str:
    return env.get("OBJECT_STORAGE_PROVIDER", "r2").strip() or "r2"


def _check_object_storage_provider(env: Mapping[str, str]) -> CheckResult:
    provider = _object_storage_provider(env)
    allowed = {"r2", "aws_s3", "minio"}
    if provider not in allowed:
        return CheckResult(
            name="OBJECT_STORAGE_PROVIDER",
            ok=False,
            detail=f"must be one of: {', '.join(sorted(allowed))}",
        )
    return CheckResult(name="OBJECT_STORAGE_PROVIDER", ok=True, detail=provider)


def _check_object_storage_endpoint(env: Mapping[str, str]) -> CheckResult:
    provider = _object_storage_provider(env)
    endpoint_url = env.get("OBJECT_STORAGE_ENDPOINT_URL", "").strip()
    if provider in {"r2", "minio"} and not endpoint_url:
        return CheckResult(
            name="OBJECT_STORAGE_ENDPOINT_URL",
            ok=False,
            detail=f"required when OBJECT_STORAGE_PROVIDER={provider}",
        )
    return CheckResult(
        name="OBJECT_STORAGE_ENDPOINT_URL",
        ok=True,
        detail=endpoint_url or "using provider default endpoint",
    )


def _check_optional_sources(env: Mapping[str, str]) -> CheckResult:
    configured = [key for key in OPTIONAL_SOURCE_ENV if env.get(key, "").strip()]
    missing = [key for key in OPTIONAL_SOURCE_ENV if key not in configured]
    if not configured:
        return CheckResult(
            name="source credentials",
            ok=True,
            detail="none set; source jobs requiring credentials will fail until configured",
        )
    return CheckResult(
        name="source credentials",
        ok=True,
        detail=f"set: {', '.join(configured)}; unset optional: {', '.join(missing)}",
    )


def _check_postgres_connection(env: Mapping[str, str]) -> CheckResult:
    try:
        with psycopg.connect(env["DAGSTER_POSTGRES_URL"], connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic command.
        return CheckResult(name="dagster postgres connection", ok=False, detail=str(exc))
    return CheckResult(name="dagster postgres connection", ok=True, detail="select 1 succeeded")


def _check_object_storage_connection(env: Mapping[str, str]) -> CheckResult:
    try:
        client = boto3.client(
            "s3",
            aws_access_key_id=env["OBJECT_STORAGE_ACCESS_KEY_ID"],
            aws_secret_access_key=env["OBJECT_STORAGE_SECRET_ACCESS_KEY"],
            region_name=env["OBJECT_STORAGE_REGION"],
            endpoint_url=env.get("OBJECT_STORAGE_ENDPOINT_URL") or None,
            config=Config(
                s3={
                    "addressing_style": "path"
                    if _truthy(env.get("OBJECT_STORAGE_USE_PATH_STYLE", "true"))
                    else "auto"
                }
            ),
        )
        client.head_bucket(Bucket=env["OBJECT_STORAGE_BUCKET"])
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic command.
        return CheckResult(name="object storage connection", ok=False, detail=str(exc))
    return CheckResult(
        name="object storage connection",
        ok=True,
        detail=f"bucket exists: {env['OBJECT_STORAGE_BUCKET']}",
    )


def _check_clickhouse_connection(env: Mapping[str, str]) -> CheckResult:
    try:
        client = clickhouse_connect.get_client(
            host=env["CLICKHOUSE_HOST"],
            port=int(env["CLICKHOUSE_PORT"]),
            username=env["CLICKHOUSE_USER"],
            password=env["CLICKHOUSE_PASSWORD"],
            database=env["CLICKHOUSE_DATABASE"],
            secure=_truthy(env["CLICKHOUSE_SECURE"]),
        )
        client.command("SELECT 1")
        client.close()
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic command.
        return CheckResult(name="clickhouse connection", ok=False, detail=str(exc))
    return CheckResult(
        name="clickhouse connection",
        ok=True,
        detail=f"{env['CLICKHOUSE_HOST']}:{env['CLICKHOUSE_PORT']}",
    )


def _optional_value(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key, "").strip()
    return value or None


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


if __name__ == "__main__":
    sys.exit(main())
