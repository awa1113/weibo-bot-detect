# 微博方向社交机器人检测V1.0

from __future__ import annotations

import torch
from torch import nn


class TextFusionClassifier(nn.Module):
    def __init__(
        self,
        description_dim: int = 768,
        tweet_dim: int = 768,
        hidden_dim: int = 256,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.description_encoder = nn.Sequential(
            nn.Linear(description_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.tweet_encoder = nn.Sequential(
            nn.Linear(tweet_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.gate = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 2),
        )
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 2),
        )

    def forward(self, description_embedding: torch.Tensor, tweet_embedding: torch.Tensor) -> torch.Tensor:
        description_state = self.description_encoder(description_embedding)
        tweet_state = self.tweet_encoder(tweet_embedding)
        merged_state = torch.cat((description_state, tweet_state), dim=1)
        gate_scores = torch.softmax(self.gate(merged_state), dim=1)
        gated_description = description_state * gate_scores[:, 0].unsqueeze(1)
        gated_tweet = tweet_state * gate_scores[:, 1].unsqueeze(1)
        return self.classifier(torch.cat((gated_description, gated_tweet), dim=1))
