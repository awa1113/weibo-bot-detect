# 微博方向社交机器人检测V1.0

from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import numpy as np
import torch
from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer

from app.core.config import get_settings


settings = get_settings()
TOKEN_PATTERN = __import__("re").compile(r"\b\w+\b", __import__("re").UNICODE)


def _hashed_embedding(text: str, dimension: int = 768) -> np.ndarray:
    vector = np.zeros(dimension, dtype=np.float32)
    tokens = TOKEN_PATTERN.findall((text or "").lower())
    if not tokens:
        return vector
    for token in tokens:
        slot = hash(token) % dimension
        sign = -1.0 if hash(f"{token}!sign") % 2 else 1.0
        vector[slot] += sign
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector


class MeanPoolingEncoder:
    def __init__(self, model_name: str, max_length: int = 128) -> None:
        self.model_name = model_name
        self.max_length = max_length
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.available = settings.enable_transformers
        self.hidden_size = 768
        if self.available:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=settings.cache_dir)
                self.model = AutoModel.from_pretrained(model_name, cache_dir=settings.cache_dir)
                self.model.to(self.device)
                self.model.eval()
                self.hidden_size = int(self.model.config.hidden_size)
            except Exception:
                self.available = False
                self.tokenizer = None
                self.model = None
        else:
            self.tokenizer = None
            self.model = None
        if self.available is False and self.tokenizer is None:
            return

    @torch.inference_mode()
    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((1, self.hidden_size), dtype=np.float32)
        if not self.available:
            return np.stack([_hashed_embedding(text, self.hidden_size) for text in texts], axis=0)
        encoded = self.tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=self.max_length,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        outputs = self.model(**encoded)
        hidden_state = outputs.last_hidden_state
        attention_mask = encoded["attention_mask"].unsqueeze(-1)
        pooled = (hidden_state * attention_mask).sum(dim=1) / attention_mask.sum(dim=1).clamp(min=1)
        return pooled.detach().cpu().numpy().astype(np.float32)


class PerplexityScorer:
    def __init__(self, model_name: str) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.available = settings.enable_transformers
        if self.available:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=settings.cache_dir)
                self.model = AutoModelForCausalLM.from_pretrained(model_name, cache_dir=settings.cache_dir)
                self.model.to(self.device)
                self.model.eval()
                if self.tokenizer.pad_token is None:
                    self.tokenizer.pad_token = self.tokenizer.eos_token
            except Exception:
                self.available = False
                self.tokenizer = None
                self.model = None
        else:
            self.tokenizer = None
            self.model = None

    @torch.inference_mode()
    def score(self, text: str) -> float:
        if not text.strip():
            return 0.0
        if not self.available:
            tokens = TOKEN_PATTERN.findall(text.lower())
            unique_ratio = len(set(tokens)) / max(len(tokens), 1)
            return round(max(5.0, 60.0 * (1.0 - unique_ratio)), 4)
        encoded = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        output = self.model(**encoded, labels=encoded["input_ids"])
        loss_value = float(output.loss.detach().cpu().item())
        perplexity = float(torch.exp(torch.tensor(loss_value)).item())
        return min(perplexity, 1_000.0)


@lru_cache(maxsize=1)
def get_description_encoder() -> MeanPoolingEncoder:
    return MeanPoolingEncoder(settings.description_model_name, max_length=96)


@lru_cache(maxsize=1)
def get_tweet_encoder() -> MeanPoolingEncoder:
    return MeanPoolingEncoder(settings.tweet_model_name, max_length=128)


@lru_cache(maxsize=1)
def get_perplexity_scorer() -> PerplexityScorer:
    return PerplexityScorer(settings.perplexity_model_name)


def aggregate_tweet_embedding(texts: Iterable[str]) -> np.ndarray:
    normalized_texts = [text.strip() for text in texts if text and text.strip()]
    if not normalized_texts:
        return np.zeros(768, dtype=np.float32)
    embeddings = get_tweet_encoder().encode(normalized_texts[:10])
    return embeddings.mean(axis=0)


def description_embedding(text: str) -> np.ndarray:
    return get_description_encoder().encode([text])[0]
