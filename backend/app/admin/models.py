from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class OrganizationListResponse(BaseModel):
    id: str
    name: str
    owner_email: str
    user_count: int
    max_users: int
    subscription_status: str
    seats: int
    created_at: datetime


class OrgUserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    daily_token_limit: int
    tokens_used_today: int
    usage_percentage: float
    last_login: Optional[datetime]


class OrgDetailResponse(BaseModel):
    id: str
    name: str
    owner_email: str
    user_count: int
    max_users: int
    subscription_status: str
    created_at: datetime
    users: List[OrgUserResponse]


class UpdateOrgRequest(BaseModel):
    max_users: Optional[int] = None


class UpdateSubscriptionRequest(BaseModel):
    status: str


class CreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    first_name: str
    last_name: str
    org_mode: Literal["new", "existing"]
    org_name: Optional[str] = None  # required when org_mode='new'
    org_id: Optional[str] = None  # required when org_mode='existing'
    daily_token_limit: int = 100000


class CreateUserResponse(BaseModel):
    user_id: str
    email: str
    organization_id: str
    organization_name: str


class UpdateUserRequest(BaseModel):
    daily_token_limit: Optional[int] = None


class UserDetailResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    organization_id: Optional[str]
    organization_name: Optional[str]
    role: str
    daily_token_limit: int


class OrganizationMemberResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    joined_at: datetime
