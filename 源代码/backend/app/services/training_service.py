# 微博方向社交机器人检测V1.0

from __future__ import annotations

import json
from datetime import datetime

from app.core.config import get_settings
from app.schemas import ModelStatusResponse
from app.services.storage_service import get_latest_training_run, save_training_run


settings = get_settings()


def get_model_status() -> ModelStatusResponse:
    notes = "当前尚未检测到训练后的权重文件，可先使用规则与文本融合的回退模式。"
    metrics: dict[str, object] = {}
    updated_at: str | None = None
    if settings.metadata_path.exists():
        payload = json.loads(settings.metadata_path.read_text(encoding="utf-8"))
        metrics = payload.get("metrics", {})
        updated_at = payload.get("updated_at")
        notes = payload.get("notes", "已加载训练元数据。")
    elif (latest_run := get_latest_training_run()) is not None:
        metrics = latest_run.get("metrics", {})
        updated_at = latest_run.get("updated_at")
        notes = latest_run.get("notes", notes)

    return ModelStatusResponse(
        available=settings.model_path.exists(),
        model_name="TextFusionClassifier",
        updated_at=updated_at,
        metrics=metrics,
        notes=notes,
    )


def record_training_metadata(metrics: dict[str, object], notes: str) -> None:
    payload = {
        "metrics": metrics,
        "updated_at": datetime.now().isoformat(),
        "notes": notes,
    }
    settings.metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_training_run(
        run_id=datetime.now().strftime("%Y%m%d%H%M%S"),
        created_at=payload["updated_at"],
        payload=payload,
    )
