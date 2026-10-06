from datetime import datetime
from typing import LiteralString, Optional

from pydantic import AwareDatetime, BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class NewsArticle(SQLModel, table=True):
    __tablename__: LiteralString = "news_articles"

    id: int = Field(primary_key=True)

    url: str = Field(max_length=255)
    headline: str = Field(max_length=255)
    thumbnail_url: Optional[str] = Field(default=None, max_length=255)
    thumbnail_base64: Optional[str] = Field(default=None)
    publish_date: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class NewsArticleResponse(BaseModel):
    id: int
    url: str
    headline: str
    thumbnail_url: str
    thumbnail_base64: str | None
    publish_date: AwareDatetime | None


class NewsListResponse(BaseModel):
    articles: list[NewsArticleResponse]
    total: int
    limit: int
    offset: int


class NewsSummarySection(BaseModel):
    title: str
    bullets: list[str] = PydanticField(default_factory=list)


class NewsSummaryDraft(BaseModel):
    macro: NewsSummarySection
    real_estate: NewsSummarySection


class NewsSummaryResponse(NewsSummaryDraft):
    generated_at: AwareDatetime
    article_count: int
