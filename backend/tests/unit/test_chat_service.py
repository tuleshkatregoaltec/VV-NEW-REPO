import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.chat.models import Conversation, Message
from app.chat.service import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            SQLModel.metadata.create_all,
            tables=[Conversation.__table__, Message.__table__],
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_conversation_deletes_messages(db_session):
    conversation = await create_conversation(
        db_session,
        user_id="user-1",
        organization_id="org-1",
        title="Conversation to delete",
    )
    assert conversation.id is not None

    await add_message(db_session, conversation.id, "user", "show me some sales listings")
    await add_message(db_session, conversation.id, "assistant", "Here are matching listings")

    assert await delete_conversation(db_session, conversation.id, "user-1") is True

    assert await get_conversation(db_session, conversation.id, "user-1") is None
    assert await get_conversation_messages(db_session, conversation.id) == []


@pytest.mark.asyncio
async def test_delete_conversation_enforces_owner(db_session):
    conversation = await create_conversation(
        db_session,
        user_id="user-1",
        organization_id="org-1",
        title="Private conversation",
    )
    assert conversation.id is not None
    await add_message(db_session, conversation.id, "user", "private message")

    assert await delete_conversation(db_session, conversation.id, "user-2") is False

    assert await get_conversation(db_session, conversation.id, "user-1") is not None
    assert len(await get_conversation_messages(db_session, conversation.id)) == 1
