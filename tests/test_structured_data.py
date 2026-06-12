"""structured_data の単体テスト。

実ネットワークには一切依存しない。
"""

from __future__ import annotations

import pytest

from ai_audit.checks import structured_data
from ai_audit.checks.base import Severity
from tests.conftest import make_target, read_fixture


# --- _extract_jsonld_blocks(純粋関数) ----------------------------------------


def test_extract_basic_organization():
    html = read_fixture("page_jsonld_organization.html")
    blocks = structured_data._extract_jsonld_blocks(html)
    assert len(blocks) == 1
    assert blocks[0]["@type"] == "Organization"
    assert blocks[0]["name"] == "Example Corp"


def test_extract_graph_expands_to_individual_blocks():
    html = read_fixture("page_jsonld_graph.html")
    blocks = [b for b in structured_data._extract_jsonld_blocks(html) if b is not None]
    types = [b.get("@type") for b in blocks]
    assert "Organization" in types
    assert "Article" in types


def test_extract_broken_json_returns_none_marker():
    html = read_fixture("page_jsonld_broken.html")
    raw = structured_data._extract_jsonld_blocks(html)
    assert None in raw  # 解析失敗マーカー


def test_extract_no_jsonld_returns_empty():
    html = "<html><head></head><body>テスト</body></html>"
    assert structured_data._extract_jsonld_blocks(html) == []


def test_extract_array_root():
    # ルートが配列の場合も展開される
    html = (
        '<script type="application/ld+json">'
        '[{"@type":"Organization","name":"A","url":"https://a.com"},'
        ' {"@type":"Article","headline":"H","author":"B","datePublished":"2026-01-01"}]'
        "</script>"
    )
    blocks = [b for b in structured_data._extract_jsonld_blocks(html) if b is not None]
    assert len(blocks) == 2


# --- _normalize_type ----------------------------------------------------------


def test_normalize_type_string():
    assert structured_data._normalize_type("Article") == ["Article"]


def test_normalize_type_list():
    assert structured_data._normalize_type(["Article", "NewsArticle"]) == [
        "Article",
        "NewsArticle",
    ]


def test_normalize_type_url():
    assert structured_data._normalize_type("https://schema.org/Article") == ["Article"]


def test_normalize_type_none_returns_empty():
    assert structured_data._normalize_type(None) == []


# --- _check_required_props ---------------------------------------------------


def test_required_props_organization_complete():
    obj = {"@type": "Organization", "name": "A", "url": "https://a.com"}
    assert structured_data._check_required_props(obj, "Organization") == []


def test_required_props_organization_missing_url():
    obj = {"@type": "Organization", "name": "A"}
    missing = structured_data._check_required_props(obj, "Organization")
    assert "url" in missing


def test_required_props_article_missing_author_and_date():
    obj = {"@type": "Article", "headline": "Test"}
    missing = structured_data._check_required_props(obj, "Article")
    assert "author" in missing
    assert "datePublished" in missing


def test_required_props_org_subtype_treated_as_organization():
    # LocalBusiness は Organization のサブタイプ → Organization の必須プロパティを検査
    obj = {"@type": "LocalBusiness", "name": "店名"}
    missing = structured_data._check_required_props(obj, "LocalBusiness")
    assert "url" in missing


def test_required_props_unknown_type_no_requirements():
    obj = {"@type": "Thing", "name": "something"}
    assert structured_data._check_required_props(obj, "Thing") == []


# --- run() 正常系 -------------------------------------------------------------


def test_run_no_jsonld_scores_zero():
    # JSON-LD が無い → 0点、WARNING
    html = "<html><head></head><body>テスト</body></html>"
    result = structured_data.run(make_target(html=html))
    assert result.score == 0
    assert any(f.severity == Severity.WARNING for f in result.findings)
    assert any("JSON-LD" in f.message for f in result.findings)


def test_run_complete_organization_scores_80():
    # Organization が必須プロパティ込みで完全 → 60+20=80点
    html = read_fixture("page_jsonld_organization.html")
    result = structured_data.run(make_target(html=html))
    assert result.score == 80
    assert not result.skipped


def test_run_complete_article_scores_80():
    # Article が必須プロパティ込みで完全 → 60+20=80点
    html = read_fixture("page_jsonld_article.html")
    result = structured_data.run(make_target(html=html))
    assert result.score == 80


def test_run_graph_with_two_complete_types_scores_90():
    # Organization + Article が両方完全 → 60+20+10=90点
    html = read_fixture("page_jsonld_graph.html")
    result = structured_data.run(make_target(html=html))
    assert result.score == 90


def test_run_faqpage_complete_scores_80():
    html = read_fixture("page_jsonld_faqpage.html")
    result = structured_data.run(make_target(html=html))
    assert result.score == 80


def test_run_missing_props_scores_60():
    # Organization だが url が無い → 必須未達 → ボーナス無し → 60点
    html = read_fixture("page_jsonld_missing_props.html")
    result = structured_data.run(make_target(html=html))
    assert result.score == 60
    assert any("url" in f.message for f in result.findings)
    assert any(f.severity == Severity.WARNING for f in result.findings)


def test_run_missing_props_has_self_recommendation():
    html = read_fixture("page_jsonld_missing_props.html")
    result = structured_data.run(make_target(html=html))
    assert any(r.effort == "self" for r in result.recommendations)


def test_run_broken_json_scores_zero_with_critical():
    # JSON構文エラー → 0点、CRITICAL
    html = read_fixture("page_jsonld_broken.html")
    result = structured_data.run(make_target(html=html))
    assert result.score == 0
    assert any(f.severity == Severity.CRITICAL for f in result.findings)


def test_run_detected_types_listed_in_findings():
    html = read_fixture("page_jsonld_organization.html")
    result = structured_data.run(make_target(html=html))
    type_finding = next(
        (f for f in result.findings if "Organization" in f.message), None
    )
    assert type_finding is not None


def test_run_page_basic_no_jsonld_warns():
    # 既存フィクスチャ(JSON-LD無し) → WARNING
    html = read_fixture("page_basic.html")
    result = structured_data.run(make_target(html=html))
    assert result.score == 0
    assert any(f.severity == Severity.WARNING for f in result.findings)
