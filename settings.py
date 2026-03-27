from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    auth0_domain: str = Field(default="", alias="AUTH0_DOMAIN")
    auth0_audience: str = Field(default="", alias="AUTH0_AUDIENCE")
    auth0_m2m_client_id: str = Field(default="", alias="AUTH0_M2M_CLIENT_ID")
    auth0_m2m_client_secret: str = Field(default="", alias="AUTH0_M2M_CLIENT_SECRET")

    airbyte_api_url: str = Field(default="https://api.airbyte.com/v1", alias="AIRBYTE_API_URL")
    airbyte_api_key: str = Field(default="", alias="AIRBYTE_API_KEY")
    airbyte_connection_id: str = Field(default="", alias="AIRBYTE_CONNECTION_ID")
    airbyte_synced_brand_json_path: str = Field(default="", alias="AIRBYTE_SYNCED_BRAND_JSON_PATH")

    ghost_api_url: str = Field(default="", alias="GHOST_API_URL")
    ghost_admin_api_key: str = Field(default="", alias="GHOST_ADMIN_API_KEY")
    ghost_api_version: str = Field(default="v6.0", alias="GHOST_API_VERSION")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")

    watchable_api_url: str = Field(default="http://localhost:8000", alias="WATCHABLE_API_URL")
    watchable_agent_token: str = Field(default="", alias="WATCHABLE_AGENT_TOKEN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
