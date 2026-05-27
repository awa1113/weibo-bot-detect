# 微博方向社交机器人检测V1.0

from __future__ import annotations

from app.schemas import FeatureSnapshot


def build_summary(username: str, final_probability: float, features: FeatureSnapshot) -> tuple[str, str, str, str]:
    risk_level = "低风险"
    label = "疑似真人"
    if final_probability >= 0.75:
        risk_level = "高风险"
        label = "高疑似社交机器人"
    elif final_probability >= 0.45:
        risk_level = "中风险"
        label = "存在自动化嫌疑"

    reasons: list[str] = []
    if features.account["posts_per_day"] > 20:
        reasons.append("发博频率异常偏高")
    if features.content["original_post_ratio"] < 0.45:
        reasons.append("原创微博占比偏低")
    if features.ai["tweet_similarity_sum"] > 0.78:
        reasons.append("历史微博内容相似度偏高")
    if features.ai["mean_perplexity"] and features.ai["mean_perplexity"] < 18:
        reasons.append("文本困惑度偏低")
    if features.account["followers_following_ratio"] < 0.2:
        reasons.append("粉丝与关注关系失衡")

    reason_text = "；".join(reasons[:3]) if reasons else "公开行为特征未出现明显自动化模式"
    summary = f"账号@{username}的综合风险分值为{final_probability:.2f}，系统判定为“{label}”。当前最突出的信号包括：{reason_text}。"

    if risk_level == "高风险":
        recommendation = "建议继续抓取更长时间窗口的数据，并结合人工复核账号主页、互动对象与外链行为。"
    elif risk_level == "中风险":
        recommendation = "建议补充近期互动网络和更长时间序列，再进行二次检测。"
    else:
        recommendation = "建议保留当前检测记录，如后续行为模式发生明显变化可再次执行复检。"

    return label, risk_level, summary, recommendation
