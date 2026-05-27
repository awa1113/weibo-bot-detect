# 微博方向社交机器人检测V1.0

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    token: str
    display_name: str


class TweetRecord(BaseModel):
    tweet_id: str
    text: str
    created_at: datetime
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    lang: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    has_media: bool = False
    possibly_sensitive: bool = False
    is_repost: bool = False


class UserBundle(BaseModel):
    username: str
    display_name: str
    user_id: str | None = None
    description: str = ""
    created_at: datetime | None = None
    followers_count: int = 0
    following_count: int = 0
    tweet_count: int = 0
    protected: bool = False
    location: str = ""
    profile_image_url: str | None = None
    posts: list[TweetRecord] = Field(default_factory=list)


class DetectionRequest(BaseModel):
    username: str = Field(min_length=1)
    max_posts: int = Field(default=6, ge=3, le=12)


class FeatureSnapshot(BaseModel):
    account: dict[str, Any]
    behavior: dict[str, Any]
    content: dict[str, Any]
    ai: dict[str, Any]


class ScoreSnapshot(BaseModel):
    text_model_probability: float
    behavior_probability: float
    ai_content_probability: float
    final_probability: float
    final_label: str
    risk_level: str


class DetectionReport(BaseModel):
    report_id: str
    created_at: datetime
    username: str
    summary: str
    recommendation: str
    account: UserBundle
    features: FeatureSnapshot
    scores: ScoreSnapshot
    model_info: dict[str, Any]


class ReportListItem(BaseModel):
    report_id: str
    created_at: datetime
    username: str
    final_label: str
    risk_level: str
    final_probability: float
    summary: str


class DashboardResponse(BaseModel):
    total_reports: int
    high_risk_reports: int
    average_probability: float
    latest_reports: list[ReportListItem]
    latest_training: dict[str, Any] | None = None


class ModelStatusResponse(BaseModel):
    available: bool
    model_name: str
    updated_at: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class SystemSettingsPayload(BaseModel):
    bind_host: str = "0.0.0.0"
    bind_port: int = 18081
    default_max_posts: int = 6
    crawler_provider: str = "weibo_public"


class MessageResponse(BaseModel):
    message: str
