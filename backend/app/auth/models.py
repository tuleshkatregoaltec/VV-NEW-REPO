from typing import Any

from pydantic import BaseModel, EmailStr, Field


class AssistantLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AssistantSessionData(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int | None = None
    expires_at: int | None = None
    token_type: str = "bearer"
    user: dict[str, Any]


class AssistantLoginData(BaseModel):
    user: dict[str, Any]
    session: AssistantSessionData


class AssistantLoginResponse(BaseModel):
    success: bool
    error: str | None = None
    data: AssistantLoginData | None = None


class UpdateProfileRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class UpdateProfileResponse(BaseModel):
    success: bool
    first_name: str
    last_name: str


class AuthMeResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    organization_id: str | None
    organization_name: str | None
    role: str
    is_owner: bool
    subscription_status: str | None
