import warnings
from functools import cached_property
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [origin.strip() for origin in v.split(",") if origin.strip()]
    if isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.dev", "../.env.dev"),
        env_ignore_empty=True,
        extra="ignore",
    )

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Vitevue API"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    # Database
    POSTGRES_URL: PostgresDsn

    # Redis
    REDIS_URL: str  # configMap
    REDIS_PASSWORD: str  # Bitwarden Secrets

    FRONTEND_URL: AnyUrl  # configMap
    PUBLIC_API_BASE_URL: AnyUrl | None = None

    # Security
    SESSION_SECRET: str  # Bitwarden Secrets
    SERVICE_API_KEY: str  # Bitwarden Secrets

    # CORS
    ALLOWED_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []

    # Honeybadger
    HONEYBADGER_API_KEY: str | None = None
    LOGFIRE_TOKEN: str | None = None

    # OpenRouter
    OPENROUTER_API_KEY: str  # Bitwarden Secrets
    DEFAULT_CHAT_MODEL: str  # configMap

    # Auth
    AUTH_URL: AnyUrl  # configMap
    AUTH_SERVICE_ROLE_KEY: str  # Bitwarden Secrets
    FIRST_SUPERUSER: EmailStr | None = None
    FIRST_SUPERUSER_PASSWORD: str | None = None
    FIRST_SUPERUSER_RENAME_FROM: EmailStr | None = None
    FIRST_SUPERUSER_FIRST_NAME: str = "Admin"
    FIRST_SUPERUSER_LAST_NAME: str = "User"
    FIRST_SUPERUSER_AVATAR_URL: str | None = None

    # PostHog
    POSTHOG_API_KEY: str | None = None
    POSTHOG_HOST: AnyUrl | None = None

    # Object storage. Production currently uses Cloudflare R2 through the S3-compatible API.
    OBJECT_STORAGE_PROVIDER: Literal["r2", "aws_s3", "minio"] = "r2"  # configMap
    OBJECT_STORAGE_ENDPOINT_URL: AnyUrl | None = None  # configMap
    OBJECT_STORAGE_ACCESS_KEY_ID: str  # Bitwarden Secrets
    OBJECT_STORAGE_SECRET_ACCESS_KEY: str  # Bitwarden Secrets
    OBJECT_STORAGE_BUCKET: str  # configMap
    OBJECT_STORAGE_REGION: str = "auto"  # configMap
    OBJECT_STORAGE_USE_PATH_STYLE: bool = True  # configMap

    # ClickHouse
    CLICKHOUSE_HOST: str  # configMap
    CLICKHOUSE_PORT: int  # configMap
    CLICKHOUSE_USER: str  # configMap
    CLICKHOUSE_PASSWORD: str  # Bitwarden Secrets
    CLICKHOUSE_DATABASE: str  # configMap
    CLICKHOUSE_SECURE: bool = False  # configMap

    # Stripe
    STRIPE_SECRET_KEY: str  # Bitwarden Secrets
    STRIPE_WEBHOOK_SECRET: str  # Bitwarden Secrets
    STRIPE_PRICE_ID_TIER1: str  # configMap
    STRIPE_PRICE_ID_TIER2: str  # configMap

    # Frontend URLs for Stripe redirects
    FRONTEND_SUCCESS_URL: AnyUrl  # configMap
    FRONTEND_CANCEL_URL: AnyUrl  # configMap

    @cached_property
    def ALEMBIC_DATABASE_URL(self) -> str:
        database_url = str(self.POSTGRES_URL)
        if database_url.startswith("postgresql+asyncpg://"):
            return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return database_url

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        origins = [str(origin).rstrip("/") for origin in self.ALLOWED_ORIGINS]
        frontend_url = str(self.FRONTEND_URL).rstrip("/")
        if frontend_url not in origins:
            origins.append(frontend_url)
        return origins

    @computed_field  # type: ignore[prop-decorator]
    @property
    def honeybadger_enabled(self) -> bool:
        return bool(self.HONEYBADGER_API_KEY)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def logfire_enabled(self) -> bool:
        return bool(self.LOGFIRE_TOKEN)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def posthog_enabled(self) -> bool:
        return bool(self.POSTHOG_API_KEY and self.POSTHOG_HOST)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bootstrap_superuser_enabled(self) -> bool:
        return bool(self.FIRST_SUPERUSER and self.FIRST_SUPERUSER_PASSWORD)

    @field_validator("SERVICE_API_KEY")
    @classmethod
    def validate_service_api_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SERVICE_API_KEY must be at least 32 characters")
        return v

    @field_validator("SESSION_SECRET")
    @classmethod
    def validate_session_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters")
        return v

    @model_validator(mode="after")
    def validate_superuser_bootstrap(self) -> Self:
        if bool(self.FIRST_SUPERUSER) != bool(self.FIRST_SUPERUSER_PASSWORD):
            raise ValueError(
                "FIRST_SUPERUSER and FIRST_SUPERUSER_PASSWORD must both be set together"
            )
        return self

    @model_validator(mode="after")
    def validate_object_storage_endpoint(self) -> Self:
        if (
            self.OBJECT_STORAGE_PROVIDER in {"r2", "minio"}
            and self.OBJECT_STORAGE_ENDPOINT_URL is None
        ):
            raise ValueError(
                "OBJECT_STORAGE_ENDPOINT_URL must be set when OBJECT_STORAGE_PROVIDER is r2 or minio"
            )
        return self

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        default_values = {
            "SESSION_SECRET": "dev_session_secret_at_least_32_chars_long_12345",
            "SERVICE_API_KEY": "dev_service_api_key_at_least_32_chars_long_12345",
            "FIRST_SUPERUSER_PASSWORD": "admin123",
        }
        if value != default_values.get(var_name):
            return

        message = (
            f"{var_name} is using a local development default. "
            "Change it for staging and production."
        )
        if self.ENVIRONMENT == "local":
            warnings.warn(message, stacklevel=1)
            return
        raise ValueError(message)

    @model_validator(mode="after")
    def enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SESSION_SECRET", self.SESSION_SECRET)
        self._check_default_secret("SERVICE_API_KEY", self.SERVICE_API_KEY)
        self._check_default_secret("FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD)
        return self


settings = Settings()  # type: ignore
