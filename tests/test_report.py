"""レポート整形の単体テスト(ネットワーク非依存)。"""

from __future__ import annotations

from ai_audit.checks import bot_access, llms_txt
from ai_audit.checks.base import CheckResult, Finding, Recommendation, Severity
from ai_audit.report import render_report


def _sample_results():
    return [
        CheckResult(
            "bot_access",
            "AIボットのアクセス可否",
            88,
            findings=[Finding(Severity.CRITICAL, "GPTBot が robots.txt でブロック")],
            recommendations=[
                Recommendation("Disallowを見直す", effort="self", priority=90)
            ],
        ),
        CheckResult(
            "llms_txt",
            "llms.txt の整備状況",
            50,
            findings=[Finding(Severity.INFO, "llms.txt は設置されていません")],
            recommendations=[
                Recommendation("将来投資として検討", effort="self", priority=20)
            ],
        ),
    ]


def test_render_contains_overall_and_sections():
    weights = {"bot_access": bot_access.WEIGHT, "llms_txt": llms_txt.WEIGHT}
    md = render_report("https://example.com", _sample_results(), weights)
    assert "総合スコア" in md
    assert "AIボットのアクセス可否" in md
    assert "llms.txt" in md
    # 誠実性ルールの注記が必ず入る
    assert "低コストな将来投資" in md


def test_overall_score_is_weighted():
    # bot_access(88, w=2) と llms_txt(50, w=0.5) の加重平均 = (176+25)/2.5 = 80.4 → 80
    weights = {"bot_access": 2.0, "llms_txt": 0.5}
    md = render_report("https://example.com", _sample_results(), weights)
    assert "80 / 100" in md
