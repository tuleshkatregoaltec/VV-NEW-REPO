from pydantic import BaseModel, Field


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
