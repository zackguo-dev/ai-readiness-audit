"""テスト共通のヘルパー。実ネットワークには一切アクセスしない。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_audit.target import TargetSite

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_target(
    *,
    html: str = "",
    robots_txt: str | None = None,
    llms_txt: str | None = None,
    llms_full_txt: str | None = None,
    url: str = "https://example.com/",
    status: int = 200,
) -> TargetSite:
    """ネットワークを使わずに TargetSite を組み立てるテスト用ファクトリ。"""
    return TargetSite(
        url=url,
        final_url=url,
        status=status,
        headers={},
        html=html,
        robots_txt=robots_txt,
        llms_txt=llms_txt,
        llms_full_txt=llms_full_txt,
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def target_factory():
    return make_target
