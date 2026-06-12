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


def test_findings_render_as_separate_lines():
    # 回帰: trim_blocksの改行食いで所見が1行に連結されるバグの再発防止。
    # 各所見は「- 」で始まる独立した行になり、行の途中に次の箇条書きや
    # 太字見出しが張り付かないこと。
    results = [
        CheckResult(
            "bot_access",
            "AIボットのアクセス可否",
            100,
            findings=[
                Finding(Severity.INFO, "全ボットがアクセス可能です"),
                Finding(
                    Severity.INFO,
                    "robots.txt が見つかりませんでした",
                    "robots.txt(自動プログラム向けの設定ファイル)が無い場合の説明。",
                ),
            ],
            recommendations=[
                Recommendation("設定を見直す", effort="self", priority=10)
            ],
        ),
    ]
    md = render_report("https://example.com", results, {"bot_access": 1.0})
    lines = md.splitlines()
    bullet_lines = [ln for ln in lines if ln.startswith("- ")]
    # 所見2件がそれぞれ独立した行
    assert any("全ボットがアクセス可能です" == ln[2:].strip() for ln in bullet_lines)
    assert any(
        ln[2:].strip().startswith("robots.txt が見つかりませんでした")
        for ln in bullet_lines
    )
    # 行内連結が無いこと
    for ln in lines:
        assert not ("です- " in ln), f"箇条書きが連結している: {ln}"
        assert not (ln.strip() and not ln.startswith("**") and "**自分でできる" in ln and not ln.strip().startswith("**")), f"見出しが張り付いている: {ln}"
    # detailは字下げされた別の行
    assert any(ln.startswith("  ") and "設定ファイル" in ln for ln in lines)


def test_overall_score_is_weighted():
    # bot_access(88, w=2) と llms_txt(50, w=0.5) の加重平均 = (176+25)/2.5 = 80.4 → 80
    weights = {"bot_access": 2.0, "llms_txt": 0.5}
    md = render_report("https://example.com", _sample_results(), weights)
    assert "80 / 100" in md
