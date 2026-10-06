from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    object_storage_provider: str = Field(default="r2", alias="OBJECT_STORAGE_PROVIDER")
    object_storage_bucket: str = Field(default="", alias="OBJECT_STORAGE_BUCKET")
    object_storage_region: str = Field(default="auto", alias="OBJECT_STORAGE_REGION")
    object_storage_endpoint_url: str = Field(default="", alias="OBJECT_STORAGE_ENDPOINT_URL")
    object_storage_use_path_style: bool = Field(default=True, alias="OBJECT_STORAGE_USE_PATH_STYLE")
    object_storage_public_url_base: str = Field(default="", alias="OBJECT_STORAGE_PUBLIC_URL_BASE")
    object_storage_access_key_id: str = Field(default="", alias="OBJECT_STORAGE_ACCESS_KEY_ID")
    object_storage_secret_access_key: str = Field(
        default="", alias="OBJECT_STORAGE_SECRET_ACCESS_KEY"
    )
    clickhouse_host: str = Field(default="localhost", alias="CLICKHOUSE_HOST")
    clickhouse_port: int = Field(default=8123, alias="CLICKHOUSE_PORT")
    clickhouse_user: str = Field(default="default", alias="CLICKHOUSE_USER")
    clickhouse_password: str = Field(default="", alias="CLICKHOUSE_PASSWORD")
    clickhouse_database: str = Field(default="default", alias="CLICKHOUSE_DATABASE")
    clickhouse_secure: bool = Field(default=False, alias="CLICKHOUSE_SECURE")
    platform_postgres_url: str = Field(default="", alias="PLATFORM_POSTGRES_URL")
    news_feed_urls: str = Field(default="", alias="NEWS_FEED_URLS")
    news_thumbnail_prefix: str = Field(
        default="media/news/thumbnails",
        alias="NEWS_THUMBNAIL_PREFIX",
    )


settings = Settings()
