"""TargetSite の単体テスト(ネットワーク非依存)。"""

from __future__ import annotations

from ai_audit.target import normalize_url
from tests.conftest import make_target, read_fixture


def test_normalize_url_adds_https():
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("  example.com/path  ") == "https://example.com/path"


def test_normalize_url_keeps_scheme():
    assert normalize_url("http://example.com") == "http://example.com"


def test_tree_parses_basic_html():
    # 正常系: HTMLが解析でき、h1テキストが取れる
    t = make_target(html=read_fixture("page_basic.html"))
    h1 = t.tree.css_first("h1")
    assert h1 is not None
    assert "Example Corp" in h1.text()


def test_tree_handles_empty_html():
    # 壊れた入力: 空HTMLでも例外を出さない
    t = make_target(html="")
    assert t.tree.css_first("h1") is None


def test_origin_and_path():
    t = make_target(url="https://example.com/foo/bar")
    assert t.origin == "https://example.com"
    assert t.path == "/foo/bar"
