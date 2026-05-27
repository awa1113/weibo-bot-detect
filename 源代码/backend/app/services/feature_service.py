# 微博方向社交机器人检测V1.0

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from statistics import mean, variance
from typing import Iterable

import numpy as np
from textblob import TextBlob

from app.schemas import FeatureSnapshot, UserBundle
from app.services.embedding_service import get_perplexity_scorer, get_tweet_encoder


URL_PATTERN = re.compile(r"https?://\S+")
MENTION_PATTERN = re.compile(r"@[\w\u4e00-\u9fff_-]+")
HASHTAG_PATTERN = re.compile(r"#([^#]+)#")
TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)
PUNCT_PATTERN = re.compile(r"[^\w\s]", re.UNICODE)


def _mean_and_variance(values: Iterable[float]) -> tuple[float, float]:
    series = [float(value) for value in values]
    if not series:
        return 0.0, 0.0
    if len(series) == 1:
        return series[0], 0.0
    return mean(series), variance(series)


def _safe_division(left: float, right: float) -> float:
    return left / right if right else 0.0


def _lexical_diversity(text: str) -> float:
    tokens = TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def _sentiment_score(text: str) -> float:
    if not text.strip():
        return 0.0
    return float(TextBlob(text).sentiment.polarity)


def _tweet_similarity_sum(texts: list[str]) -> float:
    normalized_texts = [text.strip() for text in texts if text.strip()]
    if len(normalized_texts) < 2:
        return 0.0
    embeddings = get_tweet_encoder().encode(normalized_texts[:6])
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / np.clip(norms, 1e-8, None)
    total = 0.0
    count = 0
    for left, right in combinations(range(normalized.shape[0]), 2):
        total += float(np.dot(normalized[left], normalized[right]))
        count += 1
    return total / count if count else 0.0


def build_feature_snapshot(account: UserBundle) -> FeatureSnapshot:
    now = datetime.now(timezone.utc)
    account_age_days = 0.0
    if account.created_at is not None:
        account_age_days = max((now - account.created_at).total_seconds() / 86400, 0.0)

    posts = account.posts
    texts = [post.text for post in posts]
    likes = [post.likes for post in posts]
    retweets = [post.retweets for post in posts]
    replies = [post.replies for post in posts]
    content_lengths = [len(text.strip()) for text in texts]
    mention_counts = [len(MENTION_PATTERN.findall(text)) for text in texts]
    url_counts = [len(URL_PATTERN.findall(text)) for text in texts]
    hashtag_counts = [len(post.hashtags) if post.hashtags else len(HASHTAG_PATTERN.findall(text)) for post, text in zip(posts, texts)]
    punctuation_counts = [len(PUNCT_PATTERN.findall(text)) for text in texts]
    lexical_diversities = [_lexical_diversity(text) for text in texts]
    sentiment_scores = [_sentiment_score(text) for text in texts]
    original_ratio = _safe_division(
        sum(1 for post in posts if not post.is_repost),
        max(len(texts), 1),
    )
    media_ratio = _safe_division(sum(1 for post in posts if post.has_media), max(len(posts), 1))

    intervals_hours = []
    ordered_posts = sorted(posts, key=lambda item: item.created_at)
    for previous, current in zip(ordered_posts, ordered_posts[1:]):
        interval = abs((current.created_at - previous.created_at).total_seconds()) / 3600
        intervals_hours.append(interval)

    if account_age_days <= 0 and ordered_posts:
        account_age_days = max((now - ordered_posts[0].created_at).total_seconds() / 86400, 0.0)

    if account.created_at is not None and account_age_days > 0:
        posts_per_day = _safe_division(account.tweet_count, max(account_age_days, 1))
    elif ordered_posts:
        observed_days = max(
            abs((ordered_posts[-1].created_at - ordered_posts[0].created_at).total_seconds()) / 86400,
            1 / 24,
        )
        posts_per_day = _safe_division(len(ordered_posts), observed_days)
    else:
        posts_per_day = 0.0

    non_empty_for_ppl = [text for text in texts if text.strip()][:4]
    perplexity_scorer = get_perplexity_scorer()
    perplexities = [perplexity_scorer.score(text) for text in non_empty_for_ppl]
    similarity_sum = _tweet_similarity_sum(texts)

    likes_mean, likes_var = _mean_and_variance(likes)
    retweet_mean, retweet_var = _mean_and_variance(retweets)
    replies_mean, replies_var = _mean_and_variance(replies)
    interval_mean, interval_var = _mean_and_variance(intervals_hours)
    length_mean, length_var = _mean_and_variance(content_lengths)
    mention_mean, mention_var = _mean_and_variance(mention_counts)
    url_mean, url_var = _mean_and_variance(url_counts)
    hashtag_mean, hashtag_var = _mean_and_variance(hashtag_counts)
    punctuation_mean, punctuation_var = _mean_and_variance(punctuation_counts)
    sentiment_mean, sentiment_var = _mean_and_variance(sentiment_scores)
    lexical_mean, lexical_var = _mean_and_variance(lexical_diversities)
    perplexity_mean, perplexity_var = _mean_and_variance(perplexities)

    posting_hours = [post.created_at.hour for post in posts]
    posting_counter = Counter(posting_hours)
    dominant_posting_hour = posting_counter.most_common(1)[0][0] if posting_counter else None

    return FeatureSnapshot(
        account={
            "username_length": len(account.username),
            "description_length": len(account.description or ""),
            "account_age_days": round(account_age_days, 2),
            "followers_count": account.followers_count,
            "following_count": account.following_count,
            "tweet_count": account.tweet_count,
            "followers_following_ratio": round(_safe_division(account.followers_count, max(account.following_count, 1)), 4),
            "posts_per_day": round(posts_per_day, 4),
            "is_protected": account.protected,
            "has_location": bool(account.location.strip()),
        },
        behavior={
            "mean_likes": round(likes_mean, 4),
            "var_likes": round(likes_var, 4),
            "mean_retweets": round(retweet_mean, 4),
            "var_retweets": round(retweet_var, 4),
            "mean_replies": round(replies_mean, 4),
            "var_replies": round(replies_var, 4),
            "mean_post_interval_hours": round(interval_mean, 4),
            "var_post_interval_hours": round(interval_var, 4),
            "dominant_posting_hour": dominant_posting_hour,
            "media_ratio": round(media_ratio, 4),
        },
        content={
            "original_post_ratio": round(original_ratio, 4),
            "mean_text_length": round(length_mean, 4),
            "var_text_length": round(length_var, 4),
            "mean_mentions": round(mention_mean, 4),
            "var_mentions": round(mention_var, 4),
            "mean_urls": round(url_mean, 4),
            "var_urls": round(url_var, 4),
            "mean_hashtags": round(hashtag_mean, 4),
            "var_hashtags": round(hashtag_var, 4),
            "mean_punctuation": round(punctuation_mean, 4),
            "var_punctuation": round(punctuation_var, 4),
        },
        ai={
            "mean_sentiment": round(sentiment_mean, 4),
            "var_sentiment": round(sentiment_var, 4),
            "mean_perplexity": round(perplexity_mean, 4),
            "var_perplexity": round(perplexity_var, 4),
            "mean_lexical_diversity": round(lexical_mean, 4),
            "var_lexical_diversity": round(lexical_var, 4),
            "tweet_similarity_sum": round(similarity_sum, 4),
        },
    )


def compute_behavior_probability(features: FeatureSnapshot) -> float:
    account = features.account
    behavior = features.behavior
    content = features.content
    ai = features.ai
    score = 0.0
    if account["followers_count"] < 100 and account["following_count"] > 300:
        score += 0.2
    if account["posts_per_day"] > 20:
        score += 0.15
    if content["original_post_ratio"] < 0.45:
        score += 0.15
    if behavior["var_post_interval_hours"] < 1.2:
        score += 0.1
    if ai["tweet_similarity_sum"] > 0.82:
        score += 0.15
    if ai["mean_lexical_diversity"] < 0.42:
        score += 0.15
    if content["mean_urls"] > 1.5:
        score += 0.1
    return min(score, 0.95)


def compute_ai_probability(features: FeatureSnapshot) -> float:
    ai = features.ai
    score = 0.0
    if 0 < ai["mean_perplexity"] < 18:
        score += 0.35
    if ai["tweet_similarity_sum"] > 0.78:
        score += 0.25
    if ai["mean_lexical_diversity"] < 0.45:
        score += 0.2
    if ai["var_sentiment"] < 0.02:
        score += 0.1
    if ai["var_perplexity"] < 8:
        score += 0.1
    return min(score, 0.99)
