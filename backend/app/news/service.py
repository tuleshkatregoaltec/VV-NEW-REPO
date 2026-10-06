import os
from datetime import datetime, timezone
from inspect import isawaitable
from pathlib import Path
from urllib.parse import urlparse

import aioboto3
from dotenv import dotenv_values
from fastapi import HTTPException
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.core.openrouter import create_openrouter_model
from app.news.models import (
    NewsArticle,
    NewsArticleResponse,
    NewsListResponse,
    NewsSummaryDraft,
    NewsSummaryResponse,
)

NEWS_THUMBNAIL_PREFIX = "media/news/thumbnails/"
NEWS_THUMBNAIL_SIGNED_URL_TTL_SECONDS = 60 * 60 * 24
NEWS_SUMMARY_ARTICLE_LIMIT = 50
NEWS_SUMMARY_SYSTEM_PROMPT = """\
You write concise market intelligence for a Dubai real estate dashboard.
Use only the supplied recent headlines. Do not invent facts.

Return two sections:
- macro: central banks, rates, inflation, oil, GDP, policy, banking, capital markets, regional economy.
- real_estate: property markets, developers, rents, projects, planning, regulations, construction, Dubai/UAE real estate.

Ignore self-help, lifestyle, career advice, personal finance advice, generic investing tips, and unrelated noise.
Keep each section to 2-4 bullets. Each bullet must be direct, newsy, and under 24 words.
If there is not enough signal for a section, return one bullet saying there is no clear recent signal.
Do not use markdown.
"""

_news_summary_agent: Agent[None, NewsSummaryDraft] | None = None


def is_news_thumbnail_key(value: str | None) -> bool:
    return bool(value and value.startswith(NEWS_THUMBNAIL_PREFIX))


def news_thumbnail_url(article_id: int) -> str:
    base_url = str(settings.PUBLIC_API_BASE_URL).rstrip("/") if settings.PUBLIC_API_BASE_URL else ""
    return f"{base_url}/api/v1/news/articles/{article_id}/thumbnail"


def article_to_response(article: NewsArticle) -> NewsArticleResponse:
    publish_date = article.publish_date
    if publish_date is not None and publish_date.tzinfo is None:
        publish_date = publish_date.replace(tzinfo=timezone.utc)

    thumbnail_url = article.thumbnail_url or ""
    if is_news_thumbnail_key(thumbnail_url):
        thumbnail_url = news_thumbnail_url(article.id)

    return NewsArticleResponse(
        id=article.id,
        url=article.url,
        headline=article.headline,
        thumbnail_url=thumbnail_url,
        thumbnail_base64=article.thumbnail_base64,
        publish_date=publish_date,
    )


async def fetch_news_articles(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> NewsListResponse:
    """Fetch paginated news articles sorted by publish date."""
    stmt = select(NewsArticle).order_by(NewsArticle.publish_date.desc()).limit(limit).offset(offset)
    result = await db.exec(stmt)
    articles = result.all()

    count_result = await db.exec(select(func.count()).select_from(NewsArticle))
    total = count_result.one()

    return NewsListResponse(
        articles=[article_to_response(article) for article in articles],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_news_summary_agent() -> Agent[None, NewsSummaryDraft]:
    global _news_summary_agent
    if _news_summary_agent is None:
        _news_summary_agent = Agent(
            create_openrouter_model(),
            output_type=NewsSummaryDraft,
            model_settings={"temperature": 0.1},
            system_prompt=NEWS_SUMMARY_SYSTEM_PROMPT,
        )
    return _news_summary_agent


def article_source(url: str) -> str:
    try:
        hostname = urlparse(url).hostname
        return hostname.replace("www.", "") if hostname else "source"
    except Exception:
        return "source"


def article_prompt_line(article: NewsArticle, index: int) -> str:
    publish_date = article.publish_date
    if publish_date is not None and publish_date.tzinfo is None:
        publish_date = publish_date.replace(tzinfo=timezone.utc)
    date_label = publish_date.date().isoformat() if publish_date else "undated"
    return f"{index}. [{date_label}] {article.headline} ({article_source(article.url)})"


def fallback_news_summary(articles: list[NewsArticle]) -> NewsSummaryResponse:
    real_estate_keywords = (
        "property",
        "real estate",
        "developer",
        "rent",
        "housing",
        "villa",
        "apartment",
        "dubai",
        "construction",
        "project",
    )
    macro_keywords = (
        "rate",
        "inflation",
        "oil",
        "gdp",
        "bank",
        "market",
        "economy",
        "capital",
        "investment",
    )

    def matching_bullets(keywords: tuple[str, ...], fallback: str) -> list[str]:
        bullets: list[str] = []
        for article in articles:
            headline = article.headline.strip()
            if not headline:
                continue
            lowered = headline.lower()
            if any(keyword in lowered for keyword in keywords):
                bullets.append(headline)
            if len(bullets) == 4:
                break
        return bullets or [fallback]

    return NewsSummaryResponse(
        macro={
            "title": "Macro",
            "bullets": matching_bullets(
                macro_keywords,
                "No clear recent macro signal is available from the current news feed.",
            ),
        },
        real_estate={
            "title": "Real estate",
            "bullets": matching_bullets(
                real_estate_keywords,
                "No clear recent real estate signal is available from the current news feed.",
            ),
        },
        generated_at=datetime.now(timezone.utc),
        article_count=len(articles),
    )


async def fetch_news_summary(db: AsyncSession) -> NewsSummaryResponse:
    stmt = (
        select(NewsArticle)
        .order_by(NewsArticle.publish_date.desc())
        .limit(NEWS_SUMMARY_ARTICLE_LIMIT)
    )
    result = await db.exec(stmt)
    articles = list(result.all())

    if not articles:
        return NewsSummaryResponse(
            macro={
                "title": "Macro",
                "bullets": ["No recent macro signal is available from the current news feed."],
            },
            real_estate={
                "title": "Real estate",
                "bullets": [
                    "No recent real estate signal is available from the current news feed."
                ],
            },
            generated_at=datetime.now(timezone.utc),
            article_count=0,
        )

    prompt = (
        "Summarise these recent headlines for a dashboard user. "
        "Ignore personal finance advice, self-help, lifestyle, and generic tips.\n\n"
        + "\n".join(
            article_prompt_line(article, index) for index, article in enumerate(articles, start=1)
        )
    )

    try:
        result = await get_news_summary_agent().run(
            prompt,
            usage_limits=UsageLimits(request_limit=1),
        )
    except Exception as exc:
        return fallback_news_summary(articles)

    return NewsSummaryResponse(
        macro=result.output.macro,
        real_estate=result.output.real_estate,
        generated_at=datetime.now(timezone.utc),
        article_count=len(articles),
    )


def env_value(*names: str) -> str | None:
    env_files = [
        dotenv_values(path)
        for path in (Path.cwd() / ".env.dev", Path.cwd().parent / ".env.dev")
        if path.exists()
    ]

    for name in names:
        value = os.environ.get(name)
        if value:
            return value
        for values in env_files:
            value = values.get(name)
            if value:
                return value
    return None


def require_env(*names: str) -> str:
    value = env_value(*names)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def build_object_storage_client_kwargs() -> dict[str, str]:
    kwargs = {
        "aws_access_key_id": require_env("OBJECT_STORAGE_ACCESS_KEY_ID"),
        "aws_secret_access_key": require_env("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
        "region_name": env_value("OBJECT_STORAGE_REGION") or "auto",
    }
    endpoint_url = env_value("OBJECT_STORAGE_ENDPOINT_URL")
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return kwargs


async def signed_news_thumbnail_url(key: str) -> str:
    bucket = require_env("OBJECT_STORAGE_BUCKET")
    session = aioboto3.Session()
    async with session.client("s3", **build_object_storage_client_kwargs()) as s3:  # type: ignore[arg-type]
        try:
            signed_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=NEWS_THUMBNAIL_SIGNED_URL_TTL_SECONDS,
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Thumbnail not found") from exc
        if isawaitable(signed_url):
            signed_url = await signed_url
        return str(signed_url)


async def fetch_news_thumbnail(
    db: AsyncSession,
    article_id: int,
) -> str:
    article = await db.get(NewsArticle, article_id)
    if article is None or not is_news_thumbnail_key(article.thumbnail_url):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return await signed_news_thumbnail_url(article.thumbnail_url)
