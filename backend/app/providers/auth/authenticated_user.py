from pydantic import BaseModel, Field
from starlette.authentication import AuthCredentials, BaseUser
from supabase_auth import User


class UserAppMetadata(BaseModel):
    provider: str = Field(default="")
    providers: list[str] = Field(default_factory=list)
    is_admin: bool = Field(default=False)
    daily_token_limit: int = Field(default=500000)


class UserMetadata(BaseModel):
    first_name: str = Field(default="")
    last_name: str = Field(default="")
    avatar_url: str | None = Field(default=None)


class AuthenticatedUser(BaseUser):
    def __init__(self, jwt: str | None, user: User) -> None:
        self._jwt = jwt
        self._auth_user = user
        self._app_metadata = (
            UserAppMetadata.model_validate(user.app_metadata)
            if isinstance(user.app_metadata, dict)
            else UserAppMetadata()
        )
        self._user_metadata = (
            UserMetadata.model_validate(user.user_metadata)
            if isinstance(user.user_metadata, dict)
            else UserMetadata()
        )

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def token(self) -> str | None:
        return self._jwt

    @property
    def id(self) -> str:
        return self._auth_user.id

    @property
    def email(self) -> str:
        return self._auth_user.email or ""

    @property
    def first_name(self) -> str:
        return self._user_metadata.first_name

    @property
    def last_name(self) -> str:
        return self._user_metadata.last_name

    @property
    def avatar_url(self) -> str | None:
        return self._user_metadata.avatar_url

    @property
    def daily_token_limit(self) -> int:
        return self._app_metadata.daily_token_limit

    @property
    def created_at(self):
        return self._auth_user.created_at

    @property
    def updated_at(self):
        return self._auth_user.updated_at

    @property
    def last_login_at(self):
        return self._auth_user.last_sign_in_at

    @property
    def is_admin(self) -> bool:
        return self._app_metadata.is_admin

    def auth_credentials(self) -> AuthCredentials:
        return AuthCredentials()
