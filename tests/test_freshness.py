"""freshness の単体テスト。

実ネットワークには一切依存しない。
- sitemap.xml の HEAD リクエストは unittest.mock.patch で差し替える。
- HTMLフィクスチャはすべてインライン定義。

テスト分類:
  正常系        — 満点/高スコアになるケース
  問題検出系    — 各診断が正しく WARNING/INFO を返すケース
  スコア検証    — 減点が仕様通りに積み上がること
  壊れた入力    — 空HTML・JSON-LD 構文エラー
  CheckResult   — 返り値の構造が仕様通りであること
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_audit.checks import freshness
from ai_audit.checks.base import Severity
from tests.conftest import make_target

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

_SITEMAP_EXISTS = True
_SITEMAP_MISSING = False


def _run(html: str = "", sitemap: bool = True) -> "CheckResult":
    """sitemap._check_sitemap をモックして run() を呼ぶユーティリティ。"""
    target = make_target(html=html)
    with patch(
        "ai_audit.checks.freshness._check_sitemap", return_value=sitemap
    ):
        return freshness.run(target)


def _page(head_extra: str = "", body: str = "<h1>タイトル</h1><p>本文</p>") -> str:
    return f"<!DOCTYPE html><html><head>{head_extra}</head><body>{body}</body></html>"


# ===========================================================================
# 正常系: 満点ケース
# ===========================================================================


class TestNormalCase:
    """公開日・更新日ともに設定 + sitemap あり → 100点。"""

    def test_ogp_dates_and_sitemap_scores_100(self):
        head = (
            '<meta property="article:published_time" content="2024-01-01">'
            '<meta property="article:modified_time" content="2025-06-01">'
        )
        result = _run(_page(head_extra=head), sitemap=True)
        assert result.score == 100
        assert result.check_id == "freshness"
        assert not result.skipped

    def test_time_element_and_sitemap_scores_100(self):
        body = (
            "<h1>タイトル</h1>"
            '<time datetime="2024-01-01">2024年1月1日</time>'
            '<time datetime="2025-06-01">更新日</time>'
        )
        result = _run(_page(body=body), sitemap=True)
        assert result.score == 100

    def test_jsonld_dates_and_sitemap_scores_100(self):
        jsonld = (
            '<script type="application/ld+json">'
            '{"@type":"Article","datePublished":"2024-01-01","dateModified":"2025-06-01"}'
            "</script>"
        )
        result = _run(_page(head_extra=jsonld), sitemap=True)
        assert result.score == 100


# ===========================================================================
# 問題検出系: 日付マークアップ
# ===========================================================================


class TestNoDates:
    """公開日・更新日ともに不在: -30点 WARNING。"""

    def test_no_dates_deducts_30(self):
        result = _run(_page(), sitemap=True)
        assert result.score == 70  # 100 - 30

    def test_no_dates_is_warning(self):
        result = _run(_page(), sitemap=True)
        assert any(f.severity == Severity.WARNING for f in result.findings)

    def test_no_dates_has_recommendation(self):
        result = _run(_page(), sitemap=True)
        assert len(result.recommendations) >= 1

    def test_no_dates_finding_message_contains_key_term(self):
        result = _run(_page(), sitemap=True)
        assert any("公開日" in f.message or "更新日" in f.message for f in result.findings)


class TestPublishedOnlyNoModified:
    """公開日のみ・更新日なし: -10点 INFO。"""

    def test_published_only_deducts_10(self):
        head = '<meta property="article:published_time" content="2024-01-01">'
        result = _run(_page(head_extra=head), sitemap=True)
        assert result.score == 90  # 100 - 10

    def test_published_only_is_info(self):
        head = '<meta property="article:published_time" content="2024-01-01">'
        result = _run(_page(head_extra=head), sitemap=True)
        date_findings = [
            f for f in result.findings
            if "公開日" in f.message or "更新日" in f.message
        ]
        assert any(f.severity == Severity.INFO for f in date_findings)

    def test_published_only_finding_contains_date_value(self):
        head = '<meta property="article:published_time" content="2024-01-01">'
        result = _run(_page(head_extra=head), sitemap=True)
        assert any("2024-01-01" in f.message for f in result.findings)


class TestTimeElementFallback:
    """<time datetime> による日付取得の確認。"""

    def test_single_time_element_is_published_date_minus_10(self):
        """time 要素が1つ → 公開日のみ扱い → -10点。"""
        body = '<h1>T</h1><time datetime="2024-03-15">2024年3月15日</time>'
        result = _run(_page(body=body), sitemap=True)
        assert result.score == 90

    def test_two_time_elements_are_pub_and_mod_scores_100(self):
        """time 要素が2つ → 公開日+更新日 → 減点なし。"""
        body = (
            "<h1>T</h1>"
            '<time datetime="2024-01-01">公開</time>'
            '<time datetime="2025-01-01">更新</time>'
        )
        result = _run(_page(body=body), sitemap=True)
        assert result.score == 100

    def test_time_element_without_datetime_attr_is_ignored(self):
        """datetime 属性がない time 要素は無視される → -30点。"""
        body = "<h1>T</h1><time>2024年1月1日</time>"
        result = _run(_page(body=body), sitemap=True)
        assert result.score == 70  # 100 - 30


class TestJsonldFallback:
    """JSON-LD フォールバックの確認。"""

    def test_jsonld_published_only_deducts_10(self):
        jsonld = (
            '<script type="application/ld+json">'
            '{"@type":"Article","datePublished":"2024-05-01"}'
            "</script>"
        )
        result = _run(_page(head_extra=jsonld), sitemap=True)
        assert result.score == 90

    def test_jsonld_both_dates_no_deduction(self):
        jsonld = (
            '<script type="application/ld+json">'
            '{"@type":"Article","datePublished":"2024-05-01","dateModified":"2025-05-01"}'
            "</script>"
        )
        result = _run(_page(head_extra=jsonld), sitemap=True)
        assert result.score == 100

    def test_jsonld_parse_error_treated_as_no_dates(self):
        """JSON-LD が壊れていると日付なし扱い → -30点。"""
        jsonld = '<script type="application/ld+json">{invalid json</script>'
        result = _run(_page(head_extra=jsonld), sitemap=True)
        assert result.score == 70


# ===========================================================================
# 問題検出系: sitemap.xml
# ===========================================================================


class TestSitemapMissing:
    """sitemap.xml が存在しない: -20点 WARNING。"""

    def test_no_sitemap_deducts_20(self):
        # 日付は揃えておいて sitemap のみ欠落
        head = (
            '<meta property="article:published_time" content="2024-01-01">'
            '<meta property="article:modified_time" content="2025-01-01">'
        )
        result = _run(_page(head_extra=head), sitemap=False)
        assert result.score == 80  # 100 - 20

    def test_no_sitemap_is_warning(self):
        head = (
            '<meta property="article:published_time" content="2024-01-01">'
            '<meta property="article:modified_time" content="2025-01-01">'
        )
        result = _run(_page(head_extra=head), sitemap=False)
        sitemap_findings = [
            f for f in result.findings if "sitemap" in f.message.lower()
        ]
        assert any(f.severity == Severity.WARNING for f in sitemap_findings)

    def test_no_sitemap_has_recommendation(self):
        head = (
            '<meta property="article:published_time" content="2024-01-01">'
            '<meta property="article:modified_time" content="2025-01-01">'
        )
        result = _run(_page(head_extra=head), sitemap=False)
        assert any("sitemap" in r.text.lower() for r in result.recommendations)


class TestSitemapExists:
    """sitemap.xml が存在するケース。"""

    def test_sitemap_present_is_info_finding(self):
        head = (
            '<meta property="article:published_time" content="2024-01-01">'
            '<meta property="article:modified_time" content="2025-01-01">'
        )
        result = _run(_page(head_extra=head), sitemap=True)
        sitemap_findings = [
            f for f in result.findings if "sitemap" in f.message.lower()
        ]
        assert any(f.severity == Severity.INFO for f in sitemap_findings)


# ===========================================================================
# スコア検証: 複数問題の組み合わせ
# ===========================================================================


class TestCombinedDeductions:
    """減点が正しく積み上がること。"""

    def test_no_dates_and_no_sitemap_deducts_50(self):
        """日付なし(-30) + sitemap なし(-20) = -50点。"""
        result = _run(_page(), sitemap=False)
        assert result.score == 50  # 100 - 30 - 20

    def test_published_only_and_no_sitemap_deducts_30(self):
        """公開日のみ(-10) + sitemap なし(-20) = -30点。"""
        head = '<meta property="article:published_time" content="2024-01-01">'
        result = _run(_page(head_extra=head), sitemap=False)
        assert result.score == 70  # 100 - 10 - 20

    def test_score_never_below_zero(self):
        """最悪ケースでもスコアは 0 以下にならない。"""
        result = _run(_page(), sitemap=False)
        assert result.score >= 0


# ===========================================================================
# 壊れた入力
# ===========================================================================


class TestBrokenInput:
    """壊れた入力でもクラッシュせず CheckResult を返すこと。"""

    def test_empty_html_does_not_crash(self):
        result = _run("", sitemap=False)
        assert result is not None
        assert 0 <= result.score <= 100

    def test_empty_html_deducts_50(self):
        """空HTML = 日付なし(-30) + sitemap なし(-20) = 50点。"""
        result = _run("", sitemap=False)
        assert result.score == 50

    def test_html_without_head_does_not_crash(self):
        result = _run("<body><p>本文のみ</p></body>", sitemap=True)
        assert result is not None
        assert 0 <= result.score <= 100

    def test_multiple_jsonld_blocks_picks_first_valid(self):
        """複数の JSON-LD がある場合、最初のブロックから日付を採用する。"""
        jsonld = (
            '<script type="application/ld+json">'
            '{"@type":"WebSite","name":"サイト名"}'
            "</script>"
            '<script type="application/ld+json">'
            '{"@type":"Article","datePublished":"2024-01-01","dateModified":"2025-01-01"}'
            "</script>"
        )
        result = _run(_page(head_extra=jsonld), sitemap=True)
        # 2番目ブロックで補完されるので満点
        assert result.score == 100


# ===========================================================================
# 優先順位テスト: OGP > time 要素 > JSON-LD
# ===========================================================================


class TestDateSourcePriority:
    """OGP meta が最優先で採用されること。"""

    def test_ogp_takes_priority_over_time_element(self):
        """OGP と time 要素が1つある → OGP で公開日確定、更新日なし → -10点 INFO。

        time 要素が1つだけの場合は公開日として扱われるため、
        OGP の公開日と time の公開日が競合し、更新日は補完されない。
        """
        head = '<meta property="article:published_time" content="2024-01-01">'
        body = '<h1>T</h1><time datetime="2023-01-01">古い日付</time>'
        result = _run(_page(head_extra=head, body=body), sitemap=True)
        # OGP で pub 確定 → time 要素の1つ目は pub 扱いで mod を補完できない → -10点
        assert result.score == 90

    def test_ogp_pub_and_time_mod_complement_each_other(self):
        """OGP で公開日・time 要素で更新日が補完されて満点。"""
        head = '<meta property="article:published_time" content="2024-01-01">'
        body = (
            "<h1>T</h1>"
            '<time datetime="ignore">1st</time>'
            '<time datetime="2025-06-01">更新</time>'
        )
        # OGP で pub 確定 → time の1番目(pub=ignore)・2番目(mod=2025-06-01) で補完
        result = _run(_page(head_extra=head, body=body), sitemap=True)
        assert result.score == 100


# ===========================================================================
# CheckResult 構造の検証
# ===========================================================================


class TestResultStructure:
    """run() が返す CheckResult の構造が仕様通りであること。"""

    def test_check_id_is_freshness(self):
        result = _run()
        assert result.check_id == "freshness"

    def test_title_is_non_empty_string(self):
        result = _run()
        assert isinstance(result.title, str)
        assert len(result.title) > 0

    def test_score_is_int_in_range(self):
        result = _run()
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100

    def test_skipped_is_false_for_normal_input(self):
        result = _run()
        assert result.skipped is False

    def test_findings_is_list(self):
        result = _run()
        assert isinstance(result.findings, list)

    def test_recommendations_is_list(self):
        result = _run()
        assert isinstance(result.recommendations, list)


# ===========================================================================
# _check_sitemap ユニットテスト（httpx をモック）
# ===========================================================================


class TestCheckSitemapUnit:
    """_check_sitemap 関数自体のユニットテスト。"""

    def test_returns_true_on_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("httpx.head", return_value=mock_response):
            assert freshness._check_sitemap("https://example.com") is True

    def test_returns_false_on_404(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch("httpx.head", return_value=mock_response):
            assert freshness._check_sitemap("https://example.com") is False

    def test_returns_false_on_http_error(self):
        import httpx as _httpx
        with patch("httpx.head", side_effect=_httpx.ConnectError("timeout")):
            assert freshness._check_sitemap("https://example.com") is False

    def test_request_url_includes_sitemap_xml(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("httpx.head", return_value=mock_response) as mock_head:
            freshness._check_sitemap("https://example.com")
            called_url = mock_head.call_args[0][0]
            assert called_url == "https://example.com/sitemap.xml"
