# 微博方向社交机器人检测V1.0

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "社交机器人检测系统"
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 18081
    jwt_token: str = "demo-admin-token"
    admin_username: str = "admin"
    admin_password: str = "Admin@123"
    weibo_base_url: str = "https://m.weibo.cn"
    weibo_seed_uid: str = "2803301701"
    description_model_name: str = "distilroberta-base"
    tweet_model_name: str = "roberta-base"
    perplexity_model_name: str = "distilgpt2"
    enable_transformers: bool = False
    model_filename: str = "text_fusion_classifier.pt"
    metadata_filename: str = "model_metadata.json"
    local_model_filename: str = "text_fusion_classifier_local.pt"
    local_metadata_filename: str = "model_metadata_local.json"
    request_timeout_seconds: int = 25
    default_max_posts: int = 6

    model_config = SettingsConfigDict(
        env_prefix="BOTSYS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def storage_dir(self) -> Path:
        return self.base_dir / "storage"

    @property
    def database_path(self) -> Path:
        return self.storage_dir / "app.db"

    @property
    def reports_dir(self) -> Path:
        return self.base_dir / "artifacts" / "reports"

    @property
    def models_dir(self) -> Path:
        return self.base_dir / "artifacts" / "models"

    @property
    def cache_dir(self) -> Path:
        return self.base_dir / "artifacts" / "cache"

    @property
    def model_path(self) -> Path:
        local_candidate = self.models_dir / self.local_model_filename
        if local_candidate.exists():
            return local_candidate
        return self.models_dir / self.model_filename

    @property
    def metadata_path(self) -> Path:
        local_candidate = self.models_dir / self.local_metadata_filename
        if local_candidate.exists():
            return local_candidate
        return self.models_dir / self.metadata_filename

    @property
    def frontend_dist_dir(self) -> Path:
        return self.base_dir.parent / "frontend" / "dist"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    for path in (
        settings.storage_dir,
        settings.reports_dir,
        settings.models_dir,
        settings.cache_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings
