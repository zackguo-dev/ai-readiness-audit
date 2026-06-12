"""TargetSite — 対象サイトを1回フェッチして全checkで使い回す中核オブジェクト。

設計(承認済みスキーマ A: 一括eager取得):
- fetch() でページHTML + robots.txt + llms.txt + llms-full.txt を1秒以上あけて順に取得し、
  すべて raw text で保持する。
- HTML解析木(selectolax)は cached_property で遅延生成。
- 各checkはここに保持された取得済みデータだけを使い、原則フェッチしない
  (例外: bot_access のUA別HEADリクエスト)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cached_property
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

# 対象サイトに正体を明示するUA(負荷をかけない・robots遵守の姿勢を示す)。
DEFAULT_UA = "ai-audit/0.1 (+https://example.com/ai-audit; respects robots.txt)"


def normalize_url(url: str) -> str:
    """スキーム無し入力に https:// を補う。末尾の空白を除去。"""
    url = url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    return url


@dataclass
class TargetSite:
    url: str  # 正規化済み入力URL
    final_url: str  # リダイレクト後の最終URL
    status: int  # ページGETのHTTPステータス
    headers: dict[str, str]  # ページレスポンスヘッダ(小文字キー)
    html: str  # 静的HTML(httpx GET。JS実行前)
    robots_txt: str | None  # 無ければNone
    llms_txt: str | None
    llms_full_txt: str | None
    fetched_at: datetime
    errors: list[str] = field(default_factory=list)  # 取得失敗の記録

    @cached_property
    def tree(self) -> HTMLParser:
        """selectolaxによるHTML解析木(遅延生成)。"""
        return HTMLParser(self.html or "")

    @property
    def origin(self) -> str:
        """スキーム+ホスト(well-knownファイルのベース)。"""
        p = urlparse(self.final_url or self.url)
        return f"{p.scheme}://{p.netloc}"

    @property
    def path(self) -> str:
        """最終URLのパス(robots判定用)。空なら '/'。"""
        return urlparse(self.final_url or self.url).path or "/"

    @classmethod
    def fetch(
        cls,
        url: str,
        *,
        timeout: float = 10.0,
        retries: int = 2,
        delay: float = 1.0,
        user_agent: str = DEFAULT_UA,
    ) -> "TargetSite":
        """ページ→robots.txt→llms.txt→llms-full.txt を delay 秒以上あけて順に取得する。

        - リクエスト間は必ず delay(>=1.0)秒あける(対象サイトに負荷をかけない)。
        - 各取得はタイムアウト+リトライ付き。失敗は errors に記録して継続する。
        """
        url = normalize_url(url)
        errors: list[str] = []
        headers = {"User-Agent": user_agent}

        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=headers
        ) as client:
            # 1) 本体ページ(最初の1本なので事前sleep不要)
            status, final_url, resp_headers, html = _get_page(
                client, url, retries, delay, errors
            )
            origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"

            # 2) well-knownファイル群(各取得の前に delay 秒あける)
            time.sleep(delay)
            robots_txt = _get_optional(
                client, urljoin(origin + "/", "robots.txt"), retries, delay, errors
            )
            time.sleep(delay)
            llms_txt = _get_optional(
                client, urljoin(origin + "/", "llms.txt"), retries, delay, errors
            )
            time.sleep(delay)
            llms_full_txt = _get_optional(
                client, urljoin(origin + "/", "llms-full.txt"), retries, delay, errors
            )

        return cls(
            url=url,
            final_url=final_url,
            status=status,
            headers=resp_headers,
            html=html,
            robots_txt=robots_txt,
            llms_txt=llms_txt,
            llms_full_txt=llms_full_txt,
            fetched_at=datetime.now(timezone.utc),
            errors=errors,
        )


def _get_page(client, url, retries, delay, errors):
    """本体ページを取得。リトライ後も失敗ならエラー記録して空で返す。"""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = client.get(url)
            return (
                r.status_code,
                str(r.url),
                {k.lower(): v for k, v in r.headers.items()},
                r.text,
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(delay)
    errors.append(f"ページ取得失敗: {url} ({last_exc})")
    return (0, url, {}, "")


def _get_optional(client, url, retries, delay, errors):
    """well-knownファイルを取得。404は「不在」=None(エラー扱いしない)。

    通信エラーのみ errors に記録する。
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = client.get(url)
            if r.status_code == 200 and r.text.strip():
                return r.text
            return None  # 404等 = 不在
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(delay)
    errors.append(f"取得失敗(通信エラー): {url} ({last_exc})")
    return None
