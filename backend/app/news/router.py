from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.decorators import cached_endpoint
from app.core.dependencies import AuthContext, require_active_subscription
from app.news.models import NewsListResponse, NewsSummaryResponse
from app.news.service import fetch_news_articles, fetch_news_summary, fetch_news_thumbnail
from app.postgres import get_db_session

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.get("/articles", response_model=NewsListResponse)
@cached_endpoint(prefix="news", expire=600)
async def get_news(
    context: AuthContext = Depends(require_active_subscription),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
):
    return await fetch_news_articles(db, limit, offset)


@router.get("/summary", response_model=NewsSummaryResponse)
@cached_endpoint(prefix="news_summary", expire=900)
async def get_news_summary(
    context: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    return await fetch_news_summary(db)


@router.get("/articles/{article_id}/thumbnail")
async def get_news_thumbnail(
    article_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    url = await fetch_news_thumbnail(db, article_id)
    return RedirectResponse(
        url,
        status_code=307,
        headers={"Cache-Control": "public, max-age=86400"},
    )
