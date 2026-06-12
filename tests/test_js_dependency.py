"""js_dependency の単体テスト。

実ブラウザ・実ネットワークには一切依存しない:
render_html は monkeypatch でレンダリング後HTML(文字列)に差し替える。
"""

from __future__ import annotations

from ai_audit.checks import js_dependency
from ai_audit.checks.base import CheckResult, Severity
from ai_audit.report import render_report
from tests.conftest import make_target, read_fixture


def _page(chars: int) -> str:
    """可視テキストがちょうど chars 文字(非空白)のHTMLを作る境界値用ヘルパー。"""
    return f"<html><body><p>{'あ' * chars}</p></body></html>"


def _patch_render(monkeypatch, rendered_html: str) -> None:
    """render_html をネットワーク無しの固定文字列返却に差し替える。"""
    monkeypatch.setattr(js_dependency, "render_html", lambda *a, **k: rendered_html)


# --- テキスト抽出(純粋関数) --------------------------------------------------


def test_extract_visible_text_excludes_invisible_tags():
    # script/style/noscript/template/svg/head の中身はカウント対象外
    text = js_dependency.extract_visible_text(read_fixture("page_spa_shell.html"))
    assert "読み込み中" in text  # 可視テキストは残る
    assert "カウントされてはいけない" not in text  # script
    assert "margin" not in text  # style
    assert "JavaScriptを有効にしてください" not in text  # noscript
    assert "テンプレート内の非表示テキスト" not in text  # template
    assert "SVG内テキスト" not in text  # svg
    assert "Example SPA" not in text  # head(title)


def test_extract_visible_text_basic_page():
    # 正常系: 通常ページの本文は抽出される
    text = js_dependency.extract_visible_text(read_fixture("page_basic.html"))
    assert "中小企業向けのクラウド会計サービスです。" in text
    assert "かんたん入力" in text


def test_extract_visible_text_empty_html():
    # 壊れた入力: 空HTMLでも例外を出さず空文字
    assert js_dependency.extract_visible_text("") == ""
    assert js_dependency.text_volume(js_dependency.extract_visible_text("")) == 0


def test_extract_visible_text_garbled_input():
    # 壊れた入力: 制御文字・閉じタグ不整合でも例外を出さない
    garbled = "\x00\xff<div><p>壊れた</span></div></p><<<>>>"
    text = js_dependency.extract_visible_text(garbled)
    assert isinstance(text, str)
    assert "壊れた" in text


def test_extract_visible_text_huge_input():
    # 壊れた入力(巨大): 50万文字の本文でも落ちず、量も正確
    huge = _page(500_000)
    vol = js_dependency.text_volume(js_dependency.extract_visible_text(huge))
    assert vol == 500_000


def test_text_volume_strips_whitespace():
    # 空白・改行・タブは量に含めない(整形差で揺れない)
    assert js_dependency.text_volume("あい うえ\n\tお ") == 5
    assert js_dependency.text_volume("   \n\t  ") == 0


# --- run() 境界値(render_htmlはmonkeypatch) ----------------------------------


def test_run_zero_dependency_scores_100(monkeypatch):
    # 正常系: 静的=レンダリング後 → 依存率0%、満点、INFO
    html = _page(100)
    _patch_render(monkeypatch, html)
    result = js_dependency.run(make_target(html=html))
    assert result.check_id == "js_dependency"
    assert not result.skipped
    assert result.score == 100
    assert result.findings[0].severity == Severity.INFO


def test_run_at_warn_threshold_is_not_warning(monkeypatch):
    # 境界値: ちょうど30%は「30%超」ではないのでINFOのまま(score=70)
    _patch_render(monkeypatch, _page(100))
    result = js_dependency.run(make_target(html=_page(70)))
    assert result.score == 70
    assert result.findings[0].severity == Severity.INFO


def test_run_just_above_warn_threshold_warns(monkeypatch):
    # 問題検出系: 31% → WARNING、score=69、vendor提案あり
    _patch_render(monkeypatch, _page(100))
    result = js_dependency.run(make_target(html=_page(69)))
    assert result.score == 69
    assert result.findings[0].severity == Severity.WARNING
    assert any(r.effort == "vendor" for r in result.recommendations)


def test_run_at_critical_threshold_is_warning(monkeypatch):
    # 境界値: ちょうど60%は「60%超」ではないのでWARNING止まり(score=40)
    _patch_render(monkeypatch, _page(100))
    result = js_dependency.run(make_target(html=_page(40)))
    assert result.score == 40
    assert result.findings[0].severity == Severity.WARNING


def test_run_just_above_critical_threshold_is_critical(monkeypatch):
    # 問題検出系: 61% → CRITICAL、score=39、vendor提案あり
    _patch_render(monkeypatch, _page(100))
    result = js_dependency.run(make_target(html=_page(39)))
    assert result.score == 39
    assert result.findings[0].severity == Severity.CRITICAL
    assert any(r.effort == "vendor" for r in result.recommendations)


def test_run_static_larger_than_rendered_clamps_to_zero(monkeypatch):
    # レアケース: JSが文言を削って静的の方が多い → 依存率0%に丸めて満点
    _patch_render(monkeypatch, _page(50))
    result = js_dependency.run(make_target(html=_page(100)))
    assert result.score == 100
    assert result.findings[0].severity == Severity.INFO


def test_run_spa_fixture_detects_critical(monkeypatch):
    # 問題検出系: SPAシェル(可視テキストほぼ無し)→レンダリング後に本文出現 → CRITICAL
    _patch_render(monkeypatch, read_fixture("page_spa_rendered.html"))
    result = js_dependency.run(make_target(html=read_fixture("page_spa_shell.html")))
    assert not result.skipped
    assert result.score < 50  # 「重大」帯
    assert any(f.severity == Severity.CRITICAL for f in result.findings)


# --- graceful degradation(動的検証不可) --------------------------------------


def test_run_render_failure_is_skipped(monkeypatch):
    # render_html が例外 → 例外を外に漏らさず skipped=True、「動的検証不可」明記
    def boom(*a, **k):
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(js_dependency, "render_html", boom)
    result = js_dependency.run(make_target(html=_page(100)))
    assert result.skipped is True
    assert "RuntimeError" in result.skip_reason
    assert any("動的検証不可" in f.message for f in result.findings)
    # 対象サイト側の問題ではないので深刻度はINFO
    assert all(f.severity == Severity.INFO for f in result.findings)


def test_run_playwright_missing_is_skipped(monkeypatch):
    # Playwright未導入(ImportError)を模擬 → skipped=True
    def no_playwright(*a, **k):
        raise ImportError("No module named 'playwright'")

    monkeypatch.setattr(js_dependency, "render_html", no_playwright)
    result = js_dependency.run(make_target(html=_page(100)))
    assert result.skipped is True
    assert "ImportError" in result.skip_reason


def test_run_empty_rendered_is_skipped(monkeypatch):
    # レンダリング結果が空文字 → 誤って「依存率0%」にせずスキップ扱い
    _patch_render(monkeypatch, "")
    result = js_dependency.run(make_target(html=_page(100)))
    assert result.skipped is True
    assert any("動的検証不可" in f.message for f in result.findings)


def test_run_script_only_rendered_is_skipped(monkeypatch):
    # レンダリング結果に可視テキストが1文字も無い場合もスキップ扱い
    _patch_render(monkeypatch, "<html><body><script>var a=1;</script></body></html>")
    result = js_dependency.run(make_target(html=_page(100)))
    assert result.skipped is True


# --- レポート統合(skippedは加重平均から除外) ----------------------------------


def test_skipped_result_excluded_from_overall_score(monkeypatch):
    # bot_access=80(w=1.0) + js_dependency=skipped(w=2.0)
    # → skippedを除外して総合80。除外されない実装なら (80+0)/3 = 27 になる。
    def boom(*a, **k):
        raise RuntimeError("no browser")

    monkeypatch.setattr(js_dependency, "render_html", boom)
    skipped = js_dependency.run(make_target(html=_page(100)))
    results = [
        CheckResult("bot_access", "AIボットのアクセス可否", 80),
        skipped,
    ]
    weights = {"bot_access": 1.0, "js_dependency": js_dependency.WEIGHT}
    md = render_report("https://example.com", results, weights)
    assert "80 / 100" in md
    # skipped項目はレポート上「検証不可」として明記される
    assert "検証不可" in md
    assert "この項目は検証できませんでした" in md
