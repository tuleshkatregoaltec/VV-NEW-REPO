import inspect
from unittest.mock import AsyncMock

from fastapi import Depends

from app.core.decorators import _build_cache_key, cached_endpoint


async def _require_context():
    return {"user_id": "ignored"}


async def _get_db():
    return object()


async def test_cached_endpoint_returns_falsey_cached_payload(monkeypatch):
    get_mock = AsyncMock(return_value=[])
    set_mock = AsyncMock()
    monkeypatch.setattr("app.core.decorators.cache.get", get_mock)
    monkeypatch.setattr("app.core.decorators.cache.set", set_mock)

    called = False

    @cached_endpoint(prefix="projects")
    async def endpoint(limit: int = 20):
        nonlocal called
        called = True
        return ["fresh"]

    result = await endpoint(limit=20)

    assert result == []
    assert called is False
    set_mock.assert_not_called()


async def test_cached_endpoint_excludes_dependency_params_from_cache_key(monkeypatch):
    get_mock = AsyncMock(return_value=None)
    set_mock = AsyncMock()
    monkeypatch.setattr("app.core.decorators.cache.get", get_mock)
    monkeypatch.setattr("app.core.decorators.cache.set", set_mock)

    @cached_endpoint(prefix="news")
    async def endpoint(
        context=Depends(_require_context),
        limit: int = 20,
        offset: int = 0,
        db=Depends(_get_db),
    ):
        return {"articles": [], "total": 0, "limit": limit, "offset": offset}

    db = object()
    context = {"org_id": 1}
    result = await endpoint(context=context, limit=20, offset=5, db=db)

    assert result["offset"] == 5
    get_mock.assert_awaited_once_with('news:{"limit":20,"offset":5}')
    set_mock.assert_awaited_once()


def test_build_cache_key_ignores_dependencies():
    async def endpoint(
        context=Depends(_require_context),
        limit: int = 20,
        offset: int = 0,
        db=Depends(_get_db),
    ):
        return None

    key = _build_cache_key(
        "news",
        inspect.signature(endpoint),
        context={"ignored": True},
        limit=20,
        offset=10,
        db=object(),
    )

    assert key == 'news:{"limit":20,"offset":10}'
