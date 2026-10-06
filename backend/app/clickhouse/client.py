"""ClickHouse async client for FastAPI.

Global async client that releases GIL during I/O operations for better concurrency.
Uses server-side parameter binding ({param:Type}) for security.
"""

import logging
from typing import Any, Dict, List, Optional

import clickhouse_connect
import pandas as pd
from clickhouse_connect.driver.asyncclient import AsyncClient

from app.config import settings

logger = logging.getLogger(__name__)

# Global singleton async client
_client: Optional[AsyncClient] = None


async def get_client() -> AsyncClient:
    """Get or create global async ClickHouse client."""
    global _client
    if _client is None:
        logger.info(
            f"Initializing ClickHouse async client: {settings.CLICKHOUSE_HOST}:{settings.CLICKHOUSE_PORT}"
        )
        _client = await clickhouse_connect.get_async_client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            username=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
            secure=settings.CLICKHOUSE_SECURE,
            connect_timeout=10,
            send_receive_timeout=300,
            query_retries=2,
            compress=True,
        )
        logger.info("ClickHouse async client initialized")
    return _client


async def close_clickhouse() -> None:
    """Close global ClickHouse client and release connection pool resources."""
    global _client
    if _client is not None:
        logger.info("Closing ClickHouse client")
        await _client.close()
        _client = None


async def query(
    sql: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Execute ClickHouse query and return list of dicts.

    Uses parameter binding ({param:Type} syntax) for security.
    Always include FINAL when querying ReplacingMergeTree tables.
    """
    client = await get_client()
    result = await client.query(sql, parameters=parameters or {})
    column_names = result.column_names
    return [dict(zip(column_names, row)) for row in result.result_rows]


async def query_df(
    sql: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """
    Execute ClickHouse query and return pandas DataFrame.

    Useful for heavy aggregations. Always include FINAL for ReplacingMergeTree tables.
    """
    client = await get_client()
    return await client.query_df(sql, parameters=parameters or {})
