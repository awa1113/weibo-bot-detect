# 微博方向社交机器人检测V1.0

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.schemas import TweetRecord, UserBundle


settings = get_settings()
WEIBO_TIME_FORMAT = "%a %b %d %H:%M:%S %z %Y"
CHINA_TZ = timezone(timedelta(hours=8))
TAG_PATTERN = re.compile(r"<[^>]+>")
TOPIC_PATTERN = re.compile(r"#([^#]+)#")
CHINESE_COUNT_PATTERN = re.compile(r"(?P<number>\d+(?:\.\d+)?)(?P<unit>[万亿]?)")
UID_INPUT_PATTERN = re.compile(r"(?:/u/|/profile/)(\d+)")
# 微博移动端公开接口对UA较敏感，使用更宽松的通用浏览器标识更稳定。
USER_AGENT = "Mozilla/5.0"


def _parse_weibo_time(value: str | None) -> datetime | None:
    if not value:
        return None

    value = value.strip()
    try:
        return datetime.strptime(value, WEIBO_TIME_FORMAT)
    except ValueError:
        pass

    now = datetime.now(CHINA_TZ)
    if value == "刚刚":
        return now

    minute_match = re.fullmatch(r"(\d+)分钟前", value)
    if minute_match:
        return now - timedelta(minutes=int(minute_match.group(1)))

    hour_match = re.fullmatch(r"(\d+)小时前", value)
    if hour_match:
        return now - timedelta(hours=int(hour_match.group(1)))

    yesterday_match = re.fullmatch(r"昨天\s*(\d{1,2}):(\d{2})", value)
    if yesterday_match:
        return (now - timedelta(days=1)).replace(
            hour=int(yesterday_match.group(1)),
            minute=int(yesterday_match.group(2)),
            second=0,
            microsecond=0,
        )

    month_day_match = re.fullmatch(r"(\d{2})-(\d{2})", value)
    if month_day_match:
        return now.replace(
            month=int(month_day_match.group(1)),
            day=int(month_day_match.group(2)),
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    year_month_day_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if year_month_day_match:
        return datetime(
            int(year_month_day_match.group(1)),
            int(year_month_day_match.group(2)),
            int(year_month_day_match.group(3)),
            tzinfo=CHINA_TZ,
        )

    return None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""

    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = TAG_PATTERN.sub("", text)
    text = html.unescape(text)
    text = text.replace("\u200b", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().replace(",", "")
    match = CHINESE_COUNT_PATTERN.fullmatch(text)
    if match:
        scale = {"": 1, "万": 10_000, "亿": 100_000_000}
        return int(float(match.group("number")) * scale[match.group("unit")])

    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _detect_language(text: str) -> str | None:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None


def _extract_uid_from_text(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.isdigit():
        return stripped

    match = UID_INPUT_PATTERN.search(stripped)
    if match:
        return match.group(1)

    try:
        parsed = urlparse(stripped)
        if parsed.path:
            match = UID_INPUT_PATTERN.search(parsed.path)
            if match:
                return match.group(1)
    except ValueError:
        return None

    return None


class PublicWeiboCrawler:
    def __init__(self) -> None:
        self._timeout = httpx.Timeout(settings.request_timeout_seconds)
        self._cookie_lock = asyncio.Lock()
        self._guest_cookies: dict[str, str] = {}
        self._guest_cookie_expires_at: datetime | None = None

    async def _bootstrap_guest_cookies(self) -> tuple[dict[str, str], datetime]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = await context.new_page()
            try:
                await page.goto(
                    f"{settings.weibo_base_url}/profile/{settings.weibo_seed_uid}",
                    wait_until="domcontentloaded",
                    timeout=settings.request_timeout_seconds * 1000,
                )

                loop = asyncio.get_running_loop()
                deadline = loop.time() + 18
                cookies: list[dict[str, Any]] = []
                while loop.time() < deadline:
                    cookies = await context.cookies([settings.weibo_base_url])
                    cookie_names = {item["name"] for item in cookies}
                    if {"SUB", "SUBP", "_T_WM"}.issubset(cookie_names):
                        break
                    await page.wait_for_timeout(750)
            finally:
                await browser.close()

        cookie_map = {
            item["name"]: item["value"]
            for item in cookies
            if str(item.get("domain") or "").endswith("weibo.cn")
        }
        if not {"SUB", "SUBP", "_T_WM"}.issubset(cookie_map):
            raise ValueError("微博游客会话初始化失败，请稍后重试")

        expires_candidates = [
            datetime.fromtimestamp(item["expires"], tz=timezone.utc)
            for item in cookies
            if item.get("expires") not in (-1, None)
        ]
        expires_at = min(expires_candidates) if expires_candidates else datetime.now(timezone.utc) + timedelta(minutes=30)
        return cookie_map, expires_at

    async def _get_guest_cookies(self) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        if self._guest_cookies and self._guest_cookie_expires_at and self._guest_cookie_expires_at > now + timedelta(minutes=5):
            return dict(self._guest_cookies)

        async with self._cookie_lock:
            now = datetime.now(timezone.utc)
            if self._guest_cookies and self._guest_cookie_expires_at and self._guest_cookie_expires_at > now + timedelta(minutes=5):
                return dict(self._guest_cookies)

            cookies, expires_at = await self._bootstrap_guest_cookies()
            self._guest_cookies = cookies
            self._guest_cookie_expires_at = expires_at
            return dict(self._guest_cookies)

    async def _reset_guest_cookies(self) -> None:
        async with self._cookie_lock:
            self._guest_cookies = {}
            self._guest_cookie_expires_at = None

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        referer: str | None = None,
    ) -> dict[str, Any]:
        response = await client.get(
            f"{settings.weibo_base_url}{path}",
            params=params,
            headers={"Referer": referer or f"{settings.weibo_base_url}/"},
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise ValueError("微博公开接口返回了非JSON页面，请稍后重试") from error
        if isinstance(payload, dict) and payload.get("ok") == 0:
            raise ValueError(payload.get("msg") or "微博公开接口返回失败")
        return payload

    async def _fetch_profile_payload(self, client: httpx.AsyncClient, uid: str) -> dict[str, Any]:
        payload = await self._request_json(
            client,
            "/api/container/getIndex",
            params={"containerid": f"100505{uid}"},
            referer=f"{settings.weibo_base_url}/u/{uid}",
        )
        if payload.get("ok") != 1 or "data" not in payload or "userInfo" not in payload["data"]:
            raise ValueError("未获取到微博账号资料")
        return payload

    async def _fetch_info_payload(self, client: httpx.AsyncClient, uid: str) -> dict[str, Any]:
        return await self._request_json(
            client,
            "/api/container/getIndex",
            params={"containerid": f"230283{uid}_-_INFO"},
            referer=f"{settings.weibo_base_url}/u/{uid}",
        )

    def _extract_info_value(self, payload: dict[str, Any], field_names: set[str]) -> str:
        for card in payload.get("data", {}).get("cards", []):
            for item in card.get("card_group", []):
                item_name = str(item.get("item_name") or "")
                if item_name in field_names:
                    return str(item.get("item_content") or "").strip()
        return ""

    def _iter_user_candidates(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for card in payload.get("data", {}).get("cards", []):
            if isinstance(card.get("user"), dict):
                candidates.append(card["user"])
            for item in card.get("card_group", []):
                if isinstance(item.get("user"), dict):
                    candidates.append(item["user"])
        return candidates

    async def _search_user(self, client: httpx.AsyncClient, query: str) -> dict[str, Any]:
        payload = await self._request_json(
            client,
            "/api/container/getIndex",
            params={"containerid": f"100103type=3&q={query}"},
            referer=f"{settings.weibo_base_url}/search",
        )
        candidates = self._iter_user_candidates(payload)
        if not candidates:
            raise ValueError(f"未找到微博账号“{query}”")

        normalized_query = query.strip().lstrip("@").casefold()
        exact_match = next(
            (
                item
                for item in candidates
                if str(item.get("screen_name") or "").strip().lstrip("@").casefold() == normalized_query
            ),
            None,
        )
        return exact_match or candidates[0]

    async def _resolve_user(self, client: httpx.AsyncClient, username: str) -> tuple[str, dict[str, Any]]:
        extracted_uid = _extract_uid_from_text(username)
        if extracted_uid is not None:
            payload = await self._fetch_profile_payload(client, extracted_uid)
            return extracted_uid, payload["data"]["userInfo"]

        matched_user = await self._search_user(client, username)
        uid = str(matched_user.get("id") or "")
        if not uid:
            raise ValueError(f"未解析到微博账号“{username}”的UID")
        payload = await self._fetch_profile_payload(client, uid)
        return uid, payload["data"]["userInfo"]

    async def _fetch_status_detail(self, client: httpx.AsyncClient, post_id: str) -> dict[str, Any]:
        return await self._request_json(
            client,
            "/api/statuses/extend",
            params={"id": post_id},
            referer=f"{settings.weibo_base_url}/status/{post_id}",
        )

    def _extract_hashtags(self, detail_payload: dict[str, Any], preview_payload: dict[str, Any], text: str) -> list[str]:
        topics = detail_payload.get("topic_struct") or preview_payload.get("topic_struct") or []
        collected = [
            str(item.get("topic_title") or "").strip()
            for item in topics
            if str(item.get("topic_title") or "").strip()
        ]
        if collected:
            return collected
        return [item.strip() for item in TOPIC_PATTERN.findall(text) if item.strip()]

    async def _build_post_record(
        self,
        client: httpx.AsyncClient,
        preview_payload: dict[str, Any],
    ) -> TweetRecord | None:
        post_id = str(preview_payload.get("id") or preview_payload.get("mid") or "")
        if not post_id:
            return None

        try:
            detail_payload = await self._fetch_status_detail(client, post_id)
        except (httpx.HTTPStatusError, ValueError):
            detail_payload = preview_payload
        text = _clean_text(detail_payload.get("text") or preview_payload.get("text"))
        created_at = _parse_weibo_time(detail_payload.get("created_at") or preview_payload.get("created_at"))
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        return TweetRecord(
            tweet_id=post_id,
            text=text,
            created_at=created_at,
            likes=_parse_count(detail_payload.get("attitudes_count") or preview_payload.get("attitudes_count")),
            retweets=_parse_count(detail_payload.get("reposts_count") or preview_payload.get("reposts_count")),
            replies=_parse_count(detail_payload.get("comments_count") or preview_payload.get("comments_count")),
            lang=_detect_language(text),
            hashtags=self._extract_hashtags(detail_payload, preview_payload, text),
            has_media=bool(
                detail_payload.get("pic_num")
                or detail_payload.get("pics")
                or detail_payload.get("page_info")
                or preview_payload.get("pic_num")
                or preview_payload.get("pics")
                or preview_payload.get("page_info")
            ),
            possibly_sensitive=False,
            is_repost=bool(detail_payload.get("retweeted_status") or preview_payload.get("retweeted_status")),
        )

    async def _fetch_recent_posts(self, client: httpx.AsyncClient, uid: str, max_posts: int) -> list[TweetRecord]:
        posts: list[TweetRecord] = []
        seen_post_ids: set[str] = set()
        max_pages = max(2, (max_posts // 5) + 2)

        for page in range(1, max_pages + 1):
            payload = await self._request_json(
                client,
                "/api/container/getIndex",
                params={
                    "type": "uid",
                    "value": uid,
                    "containerid": f"107603{uid}",
                    "page": page,
                },
                referer=f"{settings.weibo_base_url}/u/{uid}",
            )
            cards = payload.get("data", {}).get("cards", [])
            if not cards:
                break

            for card in cards:
                preview_payload = card.get("mblog")
                if not isinstance(preview_payload, dict):
                    continue

                post_id = str(preview_payload.get("id") or preview_payload.get("mid") or "")
                if not post_id or post_id in seen_post_ids:
                    continue
                seen_post_ids.add(post_id)

                record = await self._build_post_record(client, preview_payload)
                if record is None:
                    continue
                if record.text.strip():
                    posts.append(record)
                if len(posts) >= max_posts:
                    return posts

        return posts

    def _build_account_bundle(
        self,
        normalized_query: str,
        user_info: dict[str, Any],
        info_payload: dict[str, Any],
        posts: list[TweetRecord],
    ) -> UserBundle:
        location = self._extract_info_value(info_payload, {"所在地", "IP属地"})
        return UserBundle(
            username=str(user_info.get("screen_name") or normalized_query),
            display_name=str(user_info.get("screen_name") or normalized_query),
            user_id=str(user_info.get("id")) if user_info.get("id") is not None else None,
            description=_clean_text(user_info.get("description")),
            created_at=None,
            followers_count=_parse_count(user_info.get("followers_count") or user_info.get("followers_count_str")),
            following_count=_parse_count(user_info.get("follow_count")),
            tweet_count=_parse_count(user_info.get("statuses_count")),
            protected=False,
            location=location,
            profile_image_url=user_info.get("avatar_hd") or user_info.get("profile_image_url"),
            posts=posts,
        )

    async def _crawl_once(self, username: str, max_posts: int, cookies: dict[str, str]) -> UserBundle:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        }
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=headers,
            cookies=cookies,
            follow_redirects=True,
        ) as client:
            normalized_query = unquote(username.strip().lstrip("@"))
            uid, user_info = await self._resolve_user(client, normalized_query)
            try:
                info_payload = await self._fetch_info_payload(client, uid)
            except (httpx.HTTPStatusError, ValueError):
                info_payload = {}
            posts = await self._fetch_recent_posts(client, uid, max_posts)
            return self._build_account_bundle(normalized_query, user_info, info_payload, posts)

    async def crawl(self, username: str, max_posts: int) -> UserBundle:
        normalized = username.strip()
        if not normalized:
            raise ValueError("请输入微博账号名称或UID")

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                cookies = await self._get_guest_cookies()
                return await self._crawl_once(normalized, max_posts, cookies)
            except (httpx.HTTPStatusError, ValueError) as error:
                last_error = error
                status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
                should_retry = status_code in {403, 432}
                if isinstance(error, ValueError) and "非JSON页面" in str(error):
                    should_retry = True
                if attempt == 0 and should_retry:
                    await self._reset_guest_cookies()
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise ValueError("微博公开数据采集失败")
