from datetime import datetime, timezone

from app.news import service
from app.news.models import NewsArticle
from app.news.service import article_to_response


def test_article_to_response_serializes_missing_thumbnail_url():
    response = article_to_response(
        NewsArticle(
            id=1,
            url="https://example.com/news",
            headline="Example headline",
            thumbnail_url=None,
            publish_date=datetime(2026, 5, 4, 12, 0, 0),
        )
    )

    assert response.thumbnail_url == ""
    assert response.publish_date == datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_article_to_response_serializes_r2_thumbnail_key_as_api_url(monkeypatch):
    monkeypatch.setattr(service.settings, "PUBLIC_API_BASE_URL", "http://localhost:8000")

    response = article_to_response(
        NewsArticle(
            id=7,
            url="https://example.com/news",
            headline="Example headline",
            thumbnail_url="media/news/thumbnails/hash/thumb.jpg",
            publish_date=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        )
    )

    assert response.thumbnail_url == "http://localhost:8000/api/v1/news/articles/7/thumbnail"
