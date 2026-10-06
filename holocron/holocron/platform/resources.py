from __future__ import annotations

from dagster import ConfigurableResource

from holocron.platform.clickhouse import ClickHouseClient
from holocron.platform.object_storage import ObjectStorageClient
from holocron.platform.settings import settings


class ObjectStorageResource(ConfigurableResource):
    def client(self) -> ObjectStorageClient:
        return ObjectStorageClient(settings)


class ClickHouseResource(ConfigurableResource):
    def client(self) -> ClickHouseClient:
        return ClickHouseClient(settings)
