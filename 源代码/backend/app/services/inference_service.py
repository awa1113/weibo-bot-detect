# 微博方向社交机器人检测V1.0

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import torch

from app.core.config import get_settings
from app.models.fusion_model import TextFusionClassifier
from app.schemas import DetectionReport, ScoreSnapshot, UserBundle
from app.services.embedding_service import aggregate_tweet_embedding, description_embedding
from app.services.feature_service import build_feature_snapshot, compute_ai_probability, compute_behavior_probability
from app.services.report_service import build_summary
from app.services.training_service import get_model_status


settings = get_settings()


class InferenceService:
    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = TextFusionClassifier().to(self.device)
        self.model.eval()
        self.model_available = False
        if settings.model_path.exists():
            state_dict = torch.load(settings.model_path, map_location=self.device)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            self.model_available = True

    def _predict_text_probability(self, account: UserBundle) -> float:
        if not account.description.strip() and not any(post.text.strip() for post in account.posts):
            return 0.0

        description_tensor = torch.tensor(
            description_embedding(account.description or ""),
            dtype=torch.float32,
            device=self.device,
        ).unsqueeze(0)
        tweet_tensor = torch.tensor(
            aggregate_tweet_embedding(post.text for post in account.posts),
            dtype=torch.float32,
            device=self.device,
        ).unsqueeze(0)

        if not self.model_available:
            similarity = torch.cosine_similarity(description_tensor, tweet_tensor).item()
            return float(max(0.0, min((1 - similarity) * 0.5, 1.0)))

        with torch.inference_mode():
            logits = self.model(description_tensor, tweet_tensor)
            probabilities = torch.softmax(logits, dim=1)
        return float(probabilities[0, 1].item())

    def detect(self, account: UserBundle) -> DetectionReport:
        features = build_feature_snapshot(account)
        text_model_probability = self._predict_text_probability(account)
        behavior_probability = compute_behavior_probability(features)
        ai_probability = compute_ai_probability(features)
        final_probability = min(text_model_probability * 0.65 + behavior_probability * 0.35, 0.99)
        final_label, risk_level, summary, recommendation = build_summary(account.username, final_probability, features)
        return DetectionReport(
            report_id=f"REP-{uuid4().hex[:10].upper()}",
            created_at=datetime.now(timezone.utc),
            username=account.username,
            summary=summary,
            recommendation=recommendation,
            account=account,
            features=features,
            scores=ScoreSnapshot(
                text_model_probability=round(text_model_probability, 4),
                behavior_probability=round(behavior_probability, 4),
                ai_content_probability=round(ai_probability, 4),
                final_probability=round(final_probability, 4),
                final_label=final_label,
                risk_level=risk_level,
            ),
            model_info=get_model_status().model_dump(),
        )
