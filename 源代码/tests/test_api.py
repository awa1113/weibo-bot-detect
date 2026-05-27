# 微博方向社交机器人检测V1.0

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.main import app  # noqa: E402
from app.schemas import TweetRecord, UserBundle  # noqa: E402
from app.services import crawler_service  # noqa: E402


def build_sample_account() -> UserBundle:
    return UserBundle(
        username="demo_bot",
        display_name="Demo Bot",
        user_id="123",
        description="Automated updates about market signals and hourly insights.",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        followers_count=12,
        following_count=980,
        tweet_count=18200,
        protected=False,
        location="",
        posts=[
            TweetRecord(
                tweet_id="1",
                text="Hourly update: signal alpha triggered. Visit https://example.com now.",
                created_at=datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc),
                likes=2,
                retweets=1,
                replies=0,
                hashtags=["signal"],
            ),
            TweetRecord(
                tweet_id="2",
                text="Hourly update: signal alpha triggered. Visit https://example.com now.",
                created_at=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
                likes=1,
                retweets=0,
                replies=0,
                hashtags=["signal"],
            ),
            TweetRecord(
                tweet_id="3",
                text="Hourly update: signal alpha triggered. Visit https://example.com now.",
                created_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
                likes=1,
                retweets=0,
                replies=0,
                hashtags=["signal"],
            ),
        ],
    )


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["message"] == "ok"


def test_login_success() -> None:
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
        assert response.status_code == 200
        assert response.json()["token"] == "demo-admin-token"


def test_login_failure() -> None:
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401


def test_settings_roundtrip() -> None:
    payload = {
        "bind_host": "0.0.0.0",
        "bind_port": 19090,
        "default_max_posts": 8,
        "crawler_provider": "weibo_public",
    }
    with TestClient(app) as client:
        update_response = client.put("/api/settings", json=payload)
        read_response = client.get("/api/settings")
        assert update_response.status_code == 200
        assert read_response.status_code == 200
        assert read_response.json()["bind_port"] == 19090


def test_dashboard_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        body = response.json()
        assert {"total_reports", "high_risk_reports", "average_probability"} <= body.keys()


def test_analyze_creates_report(monkeypatch) -> None:
    async def fake_crawl(self, username: str, max_posts: int) -> UserBundle:
        return build_sample_account()

    monkeypatch.setattr(crawler_service.PublicWeiboCrawler, "crawl", fake_crawl)

    with TestClient(app) as client:
        response = client.post("/api/analyze", json={"username": "demo_bot", "max_posts": 3})
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "demo_bot"
        assert body["scores"]["final_label"] in {"高疑似社交机器人", "存在自动化嫌疑", "疑似真人"}

        reports_response = client.get("/api/reports")
        assert reports_response.status_code == 200
        assert len(reports_response.json()) >= 1
