# 微博方向社交机器人检测V1.0

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas import (
    DashboardResponse,
    DetectionReport,
    DetectionRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    ModelStatusResponse,
    SystemSettingsPayload,
)
from app.services.crawler_service import PublicWeiboCrawler
from app.services.inference_service import InferenceService
from app.services.storage_service import (
    get_report,
    get_report_statistics,
    list_reports,
    load_settings,
    save_report,
    save_settings,
)
from app.services.training_service import get_model_status


router = APIRouter()
settings = get_settings()
crawler = PublicWeiboCrawler()
inference_service = InferenceService()


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return LoginResponse(token=settings.jwt_token, display_name="系统管理员")


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard() -> DashboardResponse:
    statistics = get_report_statistics()
    return DashboardResponse(
        total_reports=statistics["total_reports"],
        high_risk_reports=statistics["high_risk_reports"],
        average_probability=round(statistics["average_probability"], 4),
        latest_reports=list_reports(limit=6),
        latest_training=get_model_status().model_dump(),
    )


@router.get("/reports", response_model=list[DetectionReport])
def reports() -> list[DetectionReport]:
    result: list[DetectionReport] = []
    for item in list_reports(limit=50):
        report = get_report(item.report_id)
        if report is not None:
            result.append(report)
    return result


@router.get("/reports/{report_id}", response_model=DetectionReport)
def report_detail(report_id: str) -> DetectionReport:
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.post("/analyze", response_model=DetectionReport)
async def analyze(payload: DetectionRequest) -> DetectionReport:
    account = await crawler.crawl(payload.username, payload.max_posts)
    report = inference_service.detect(account)
    save_report(report)
    return report


@router.get("/training/status", response_model=ModelStatusResponse)
def training_status() -> ModelStatusResponse:
    return get_model_status()


@router.get("/settings", response_model=SystemSettingsPayload)
def read_settings() -> SystemSettingsPayload:
    return load_settings()


@router.put("/settings", response_model=SystemSettingsPayload)
def update_settings(payload: SystemSettingsPayload) -> SystemSettingsPayload:
    save_settings(payload)
    return payload


@router.get("/health", response_model=MessageResponse)
def health() -> MessageResponse:
    return MessageResponse(message="ok")
