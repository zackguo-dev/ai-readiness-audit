"""render_html / build_report_data のテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_audit.checks.base import CheckResult, Finding, Recommendation, Severity
import pytest

from ai_audit.report.renderer import (
    ReportData,
    _score_color_hex,
    _status_label,
    build_report_data,
    render_html,
    render_markdown,
    render_pdf,
    render_report,
)

_DT = datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc)


def _results():
    return [
        CheckResult(
            "js_dependency",
            "JavaScript依存度",
            10,
            findings=[Finding(Severity.CRITICAL, "JS依存率が高いです")],
            recommendations=[
                Recommendation("SSRを導入する", effort="vendor", cost_hint="10〜30万円", priority=88)
            ],
        ),
        CheckResult(
            "bot_access",
            "AIボットのアクセス可否",
            80,
            findings=[Finding(Severity.INFO, "全ボットがアクセス可能です")],
            recommendations=[Recommendation("現状維持", effort="self", priority=10)],
        ),
        CheckResult(
            "llms_txt",
            "llms.txt の整備状況",
            50,
            findings=[Finding(Severity.INFO, "llms.txt が見つかりません")],
            recommendations=[Recommendation("llms.txtを設置する", effort="self", priority=20)],
        ),
    ]


_WEIGHTS = {"js_dependency": 2.0, "bot_access": 1.5, "llms_txt": 0.5}


# ---------------------------------------------------------------------------
# _score_color_hex
# ---------------------------------------------------------------------------

class TestScoreColorHex:
    def test_red_at_0(self):
        assert _score_color_hex(0) == "#E24B4A"

    def test_red_at_39(self):
        assert _score_color_hex(39) == "#E24B4A"

    def test_amber_at_40(self):
        assert _score_color_hex(40) == "#BA7517"

    def test_amber_at_69(self):
        assert _score_color_hex(69) == "#BA7517"

    def test_green_at_70(self):
        assert _score_color_hex(70) == "#639922"

    def test_green_at_100(self):
        assert _score_color_hex(100) == "#639922"


# ---------------------------------------------------------------------------
# _status_label
# ---------------------------------------------------------------------------

class TestStatusLabel:
    def test_critical(self):
        assert _status_label(0) == "重大"
        assert _status_label(39) == "重大"

    def test_mondai_ari(self):
        assert _status_label(40) == "問題あり"
        assert _status_label(49) == "問題あり"

    def test_youkaizen(self):
        assert _status_label(50) == "要改善"
        assert _status_label(69) == "要改善"

    def test_ryoukou(self):
        assert _status_label(70) == "良好"
        assert _status_label(100) == "良好"


# ---------------------------------------------------------------------------
# build_report_data
# ---------------------------------------------------------------------------

class TestBuildReportData:
    def test_returns_report_data(self):
        data = build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)
        assert isinstance(data, ReportData)

    def test_url_and_date(self):
        data = build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)
        assert data.url == "https://example.com"
        assert data.date == "2026年6月12日"

    def test_is_primary_first(self):
        data = build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)
        assert data.checks[0].is_primary is True
        assert data.checks[0].name == "JavaScript依存度"

    def test_remaining_sorted_ascending(self):
        data = build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)
        non_primary = [c for c in data.checks if not c.is_primary]
        scores = [c.score for c in non_primary]
        assert scores == sorted(scores)

    def test_actions_sorted_by_priority_desc(self):
        data = build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)
        # priority=88 のSSR導入が先頭
        assert data.actions[0].text == "SSRを導入する"

    def test_action_type_vendor_mapped_to_professional(self):
        data = build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)
        vendor = next(a for a in data.actions if a.type == "professional")
        assert vendor.cost == "10〜30万円"

    def test_action_type_self_mapped(self):
        data = build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)
        self_actions = [a for a in data.actions if a.type == "self"]
        assert len(self_actions) == 2

    def test_skipped_check_uses_skip_reason(self):
        skipped = CheckResult("freshness", "鮮度", 50, skipped=True, skip_reason="タイムアウト")
        data = build_report_data("https://example.com", [skipped], {"freshness": 1.0}, fetched_at=_DT)
        assert data.checks[0].finding == "タイムアウト"

    def test_no_findings_returns_default_text(self):
        r = CheckResult("freshness", "鮮度", 100, findings=[], recommendations=[])
        data = build_report_data("https://x.com", [r], {"freshness": 1.0}, fetched_at=_DT)
        assert data.checks[0].finding == "問題は見つかりませんでした"

    def test_highest_severity_finding_selected(self):
        r = CheckResult(
            "bot_access", "bot", 50,
            findings=[
                Finding(Severity.INFO, "INFO所見"),
                Finding(Severity.CRITICAL, "重大所見"),
                Finding(Severity.WARNING, "警告所見"),
            ],
            recommendations=[],
        )
        data = build_report_data("https://x.com", [r], {"bot_access": 1.0}, fetched_at=_DT)
        assert data.checks[0].finding == "重大所見"


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------

class TestRenderHtml:
    def _data(self) -> ReportData:
        return build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT)

    def test_returns_html_string(self):
        html = render_html(self._data())
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_contains_url(self):
        html = render_html(self._data())
        assert "example.com" in html

    def test_contains_date(self):
        html = render_html(self._data())
        assert "2026年6月12日" in html

    def test_contains_score(self):
        data = self._data()
        html = render_html(data)
        assert f">{data.score}<" in html

    def test_contains_status_label(self):
        data = self._data()
        html = render_html(data)
        assert data.status_label in html

    def test_green_color_for_high_score(self):
        r = CheckResult("bot_access", "bot", 90, findings=[], recommendations=[])
        data = build_report_data("https://example.com", [r], {"bot_access": 1.0}, fetched_at=_DT)
        html = render_html(data)
        assert "#639922" in html

    def test_red_color_for_low_score(self):
        r = CheckResult(
            "js_dependency", "JS", 10,
            findings=[Finding(Severity.CRITICAL, "重大です")],
            recommendations=[],
        )
        data = build_report_data("https://example.com", [r], {"js_dependency": 1.0}, fetched_at=_DT)
        html = render_html(data)
        assert "#E24B4A" in html

    def test_amber_color_for_mid_score(self):
        r = CheckResult("bot_access", "bot", 55, findings=[], recommendations=[])
        data = build_report_data("https://example.com", [r], {"bot_access": 1.0}, fetched_at=_DT)
        html = render_html(data)
        assert "#BA7517" in html

    def test_primary_tag_present(self):
        html = render_html(self._data())
        assert "最重要" in html

    def test_donut_dashoffset_computed_correctly(self):
        # score=10 → dashoffset = 314 * 0.9 = 282.6
        r = CheckResult("js_dependency", "JS", 10, findings=[], recommendations=[])
        data = build_report_data("https://x.com", [r], {"js_dependency": 1.0}, fetched_at=_DT)
        html = render_html(data)
        assert "stroke-dashoffset" in html
        assert "282.6" in html

    def test_donut_dashoffset_at_100(self):
        # score=100 → dashoffset = 0.0
        r = CheckResult("bot_access", "bot", 100, findings=[], recommendations=[])
        data = build_report_data("https://x.com", [r], {"bot_access": 1.0}, fetched_at=_DT)
        html = render_html(data)
        assert "stroke-dashoffset=\"0.0\"" in html

    def test_action_text_present(self):
        html = render_html(self._data())
        assert "SSRを導入する" in html

    def test_self_action_label(self):
        html = render_html(self._data())
        assert "自社で対応可" in html

    def test_professional_action_label_with_cost(self):
        html = render_html(self._data())
        assert "制作会社へ依頼" in html
        assert "10〜30万円" in html

    def test_self_contained_no_external_deps(self):
        html = render_html(self._data())
        assert "googleapis.com" not in html
        assert "cdn." not in html
        assert "<script src" not in html
        assert "<link rel=\"stylesheet\" href=\"http" not in html

    def test_meta_charset_present(self):
        html = render_html(self._data())
        assert 'charset="UTF-8"' in html

    def test_meta_viewport_present(self):
        html = render_html(self._data())
        assert "viewport" in html


# ---------------------------------------------------------------------------
# render_pdf
# ---------------------------------------------------------------------------

try:
    import weasyprint  # noqa: F401
    _WEASYPRINT_OK = True
except (ImportError, OSError):
    _WEASYPRINT_OK = False


class TestRenderPdf:
    def _html(self) -> str:
        return render_html(build_report_data("https://example.com", _results(), _WEIGHTS, fetched_at=_DT))

    @pytest.mark.skipif(not _WEASYPRINT_OK, reason="WeasyPrint not available")
    def test_returns_bytes(self):
        pdf = render_pdf(self._html())
        assert isinstance(pdf, bytes)

    @pytest.mark.skipif(not _WEASYPRINT_OK, reason="WeasyPrint not available")
    def test_starts_with_pdf_magic_bytes(self):
        pdf = render_pdf(self._html())
        assert pdf[:4] == b"%PDF"

    def test_importerror_message_contains_instructions(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "weasyprint", None)
        with pytest.raises(ImportError, match="WeasyPrint"):
            render_pdf("<html></html>")


# ---------------------------------------------------------------------------
# render_markdown / render_report 後方互換
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_render_markdown_returns_markdown(self):
        r = CheckResult(
            "bot_access", "AIボット", 80,
            findings=[Finding(Severity.INFO, "OK")],
            recommendations=[],
        )
        md = render_markdown("https://example.com", [r], {"bot_access": 1.0})
        assert "総合スコア" in md

    def test_render_report_is_alias_for_render_markdown(self):
        assert render_report is render_markdown

    def test_existing_test_suite_still_passes(self):
        from ai_audit.checks import bot_access, llms_txt
        results = [
            CheckResult(
                "bot_access", "AIボットのアクセス可否", 88,
                findings=[Finding(Severity.CRITICAL, "GPTBot がブロック")],
                recommendations=[Recommendation("Disallowを見直す", effort="self", priority=90)],
            ),
            CheckResult(
                "llms_txt", "llms.txt の整備状況", 50,
                findings=[Finding(Severity.INFO, "llms.txt は設置されていません")],
                recommendations=[Recommendation("将来投資として検討", effort="self", priority=20)],
            ),
        ]
        weights = {"bot_access": bot_access.WEIGHT, "llms_txt": llms_txt.WEIGHT}
        md = render_report("https://example.com", results, weights)
        assert "総合スコア" in md
        assert "低コストな将来投資" in md
