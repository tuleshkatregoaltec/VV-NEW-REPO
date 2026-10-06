from datetime import datetime, timezone
from typing import Any, Dict, List, LiteralString, Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Text
from sqlmodel import JSON, Column, Field, Relationship, SQLModel


class Conversation(SQLModel, table=True):
    __tablename__: LiteralString = "conversations"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    organization_id: str = Field(index=True)
    title: Optional[str] = None
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
    )

    messages: List["Message"] = Relationship(back_populates="conversation")


class Message(SQLModel, table=True):
    __tablename__: LiteralString = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversations.id", index=True)
    role: str  # "user" | "assistant"
    content: str = Field(sa_column=Column(Text))

    meta_data: Optional[Dict[str, Any]] = Field(sa_column=Column(JSON), default={})

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    conversation: Optional[Conversation] = Relationship(back_populates="messages")


# Request/Response Schemas


class CreateConversationRequest(BaseModel):
    """Request model for creating a new conversation"""

    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Request model for sending a message in a conversation"""

    message: str


class UpdateConversationRequest(BaseModel):
    """Request model for updating a conversation"""

    title: str


class ConversationResponse(BaseModel):
    """Response model for conversation data"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Response model for list of conversations"""

    conversations: List[ConversationResponse]
    total: int


class MessageResponse(BaseModel):
    """Response model for message data"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    meta_data: Optional[Dict[str, Any]] = None
    created_at: datetime
