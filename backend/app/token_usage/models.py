from datetime import date as dt_date
from datetime import datetime, timezone
from typing import LiteralString, Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class UserTokenUsage(SQLModel, table=True):
    """Daily token usage tracking per user"""

    __tablename__: LiteralString = "user_token_usage"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Foreign key to user
    user_id: str = Field(index=True)

    # Usage tracking
    date: dt_date = Field(index=True)  # UTC date
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class UserTokenStatsResponse(BaseModel):
    """Token usage statistics for a user"""

    user_id: str
    tokens_used_today: int
    daily_limit: int
    usage_percentage: float
    remaining_tokens: int
