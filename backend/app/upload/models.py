from datetime import datetime

from pydantic import BaseModel

from app.news.models import NewsArticleResponse


class NewsArticleCreate(BaseModel):
    url: str
    headline: str
    thumbnail_url: str | None = None
    thumbnail_base64: str | None = None
    publish_date: datetime | None = None


class NewsArticleUploadResponse(BaseModel):
    created: bool
    article: NewsArticleResponse | None = None
    message: str


class NewsArticleUploadRequest(BaseModel):
    article: NewsArticleCreate


class ChunkedUploadRequest(BaseModel):
    """Query params for chunked upload endpoint."""

    source_url: str
    upload_session_id: str
    chunk_index: int
    total_chunks: int
    original_filename: str
    total_file_size: int
    chunk_size: int
    expected_hash: str | None = None


class ChunkedUploadResponse(BaseModel):
    status: str
    chunk_index: int | None = None
    total_chunks: int | None = None
    filename: str | None = None
    size: int | None = None
    hash: str | None = None
    path: str | None = None
    source_url: str | None = None
    uploaded_at: str | None = None
    session_id: str | None = None


class UploadHealthResponse(BaseModel):
    status: str
    s3: bool
    redis: bool | None = None
    error: str | None = None
