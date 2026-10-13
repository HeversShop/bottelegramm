from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    bot_token: str = Field(..., validation_alias="BOT_TOKEN")
    webapp_url: str = Field("http://localhost:5173", validation_alias="WEBAPP_URL")
    database_url: str = Field(
        "sqlite+aiosqlite:///./data/cs2_tournaments.db", validation_alias="DATABASE_URL"
    )
    auto_create_db: bool = Field(True, validation_alias="AUTO_CREATE_DB")
    cors_origins: str = Field("http://localhost:5173", validation_alias="CORS_ORIGINS")
    admin_telegram_ids: str = Field("", validation_alias="ADMIN_TELEGRAM_IDS")
    telegram_initdata_max_age: int = Field(86400, validation_alias="TELEGRAM_INITDATA_MAX_AGE")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def admin_ids(self) -> set[int]:
        result: set[int] = set()
        for item in self.admin_telegram_ids.split(","):
            item = item.strip()
            if item:
                result.add(int(item))
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()

