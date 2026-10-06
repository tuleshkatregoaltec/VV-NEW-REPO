import hashlib
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.core.cache import RedisCache
from app.core.object_storage import ObjectStorageClient
from app.news.models import NewsArticle, NewsArticleResponse
from app.upload.models import (
    ChunkedUploadResponse,
    NewsArticleCreate,
    NewsArticleUploadResponse,
)

logger = logging.getLogger(__name__)


object_storage_client = ObjectStorageClient(
    endpoint_url=(
        str(settings.OBJECT_STORAGE_ENDPOINT_URL) if settings.OBJECT_STORAGE_ENDPOINT_URL else None
    ),
    access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY_ID,
    secret_access_key=settings.OBJECT_STORAGE_SECRET_ACCESS_KEY,
    bucket_name=settings.OBJECT_STORAGE_BUCKET,
    region=settings.OBJECT_STORAGE_REGION,
    use_path_style=settings.OBJECT_STORAGE_USE_PATH_STYLE,
)


cache = RedisCache(settings.REDIS_URL, settings.REDIS_PASSWORD)


def sanitize_filename(filename: str) -> str:
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    if not safe or ".." in safe:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe


def calculate_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def create_news_article(
    db: AsyncSession,
    article_data: NewsArticleCreate,
) -> NewsArticleUploadResponse:
    stmt = select(NewsArticle).where(NewsArticle.url == article_data.url)
    result = await db.exec(stmt)
    existing_article = result.first()

    if existing_article:
        return NewsArticleUploadResponse(
            created=False,
            article=NewsArticleResponse(
                id=existing_article.id,
                url=existing_article.url,
                headline=existing_article.headline,
                thumbnail_url=existing_article.thumbnail_url or "",
                thumbnail_base64=existing_article.thumbnail_base64,
                publish_date=existing_article.publish_date.replace(tzinfo=timezone.utc),
            ),
            message="Article already exists in database",
        )

    news_article = NewsArticle(**article_data.model_dump())

    news_article.publish_date = news_article.publish_date.replace(tzinfo=timezone.utc)

    db.add(news_article)
    await db.commit()
    await db.refresh(news_article)
    await cache.clear_prefix("news")

    return NewsArticleUploadResponse(
        created=True,
        article=NewsArticleResponse(
            id=news_article.id,
            url=news_article.url,
            headline=news_article.headline,
            thumbnail_url=news_article.thumbnail_url or "",
            thumbnail_base64=news_article.thumbnail_base64,
            publish_date=news_article.publish_date.replace(tzinfo=timezone.utc),
        ),
        message="Article created successfully",
    )


async def process_chunked_upload(
    chunk: UploadFile,
    source_url: str,
    upload_session_id: str,
    chunk_index: int,
    total_chunks: int,
    original_filename: str,
    total_file_size: int,
    chunk_size: int,
    expected_hash: str | None = None,
) -> ChunkedUploadResponse:
    """
    Store chunk to object storage. Assembly is handled by the ETL node, not here.

    When all chunks are received, saves metadata.json with upload info
    for the ETL node to use during assembly.
    """
    if not 1 <= chunk_index <= total_chunks:
        raise HTTPException(400, f"Invalid chunk_index: {chunk_index}")

    safe_filename = sanitize_filename(original_filename)

    chunk_data = await chunk.read()

    # Store chunk in etl/uploads/ path for ETL node to access
    s3_key = f"etl/uploads/{upload_session_id}/chunk_{chunk_index:04d}"
    await object_storage_client.upload(s3_key, chunk_data)

    if not cache.redis:
        raise HTTPException(503, "Redis unavailable")

    redis_key = f"upload:{upload_session_id}"
    await cache.redis.sadd(redis_key, chunk_index)  # type: ignore
    await cache.redis.expire(redis_key, 3600)  # type: ignore

    logger.info(
        f"Chunk {chunk_index}/{total_chunks} uploaded to object storage for {safe_filename}"
    )

    received_count = await cache.redis.scard(redis_key)  # type: ignore

    if received_count < total_chunks:
        return ChunkedUploadResponse(
            status="chunk_received",
            chunk_index=chunk_index,
            total_chunks=total_chunks,
        )

    # All chunks received - save metadata for ETL node (no assembly here)
    logger.info(f"All {total_chunks} chunks received for {safe_filename}, saving metadata")

    try:
        import json

        metadata = {
            "session_id": upload_session_id,
            "filename": safe_filename,
            "source_url": source_url,
            "total_chunks": total_chunks,
            "total_size": total_file_size,
            "chunk_size": chunk_size,
            "expected_hash": expected_hash,
            "uploaded_at": datetime.now().isoformat(),
            "status": "pending",
        }

        metadata_key = f"etl/uploads/{upload_session_id}/metadata.json"
        await object_storage_client.upload(metadata_key, json.dumps(metadata).encode())

        await cache.delete(redis_key)

        logger.info(
            f"Metadata saved for {safe_filename} ({total_file_size:,} bytes, {total_chunks} chunks)"
        )

        return ChunkedUploadResponse(
            status="completed",
            filename=safe_filename,
            size=total_file_size,
            hash=expected_hash,
            source_url=source_url,
            uploaded_at=datetime.now().isoformat(),
            session_id=upload_session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to save metadata for {safe_filename}")
        raise HTTPException(500, f"Metadata save failed: {e}")
