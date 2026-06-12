"""semantic_html の単体テスト。

実ネットワークには一切依存しない。
HTMLフィクスチャはすべてインライン定義。

テスト分類:
  正常系  — 満点/高スコアになるケース
  問題検出系 — 各診断が正しく WARNING/CRITICAL を返すケース
  壊れた入力 — 空HTML・巨大HTML・文字化け相当の入力
"""

from __future__ import annotations

import pytest

from ai_audit.checks import semantic_html
from ai_audit.checks.base import Severity
from tests.conftest import make_target

# ---------------------------------------------------------------------------
# ヘルパー: よく使うHTMLスニペットを組み立てる
# ---------------------------------------------------------------------------

_HEAD_FULL = """
<meta name="description" content="ページの説明文が入ります。">
<meta property="og:title" content="サンプルページ">
<meta property="og:description" content="OGPの説明文です。">
"""

_HEAD_BARE = ""  # meta description も OGP も無し


def _page(
    *,
    head_extra: str = _HEAD_FULL,
    body: str = "<h1>タイトル</h1><p>本文</p>",
) -> str:
    return f"<!DOCTYPE html><html><head>{head_extra}</head><body>{body}</body></html>"


# ===========================================================================
# 正常系: セマンティックHTMLが正しく実装されているケース
# ===========================================================================


class TestNormalCase:
    """正常系 — 各チェックが減点を発生させないHTML。"""

    def test_perfect_page_scores_100(self):
        """完全なセマンティックHTMLは 100点。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body=(
                "<h1>メインタイトル</h1>"
                "<h2>セクション1</h2>"
                "<h3>サブセクション</h3>"
                '<img src="a.png" alt="説明画像">'
            ),
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 100
        assert result.check_id == "semantic_html"
        assert not result.skipped

    def test_no_images_does_not_deduct(self):
        """画像が1枚もないページは alt 欠落の減点なし。"""
        html = _page(head_extra=_HEAD_FULL, body="<h1>タイトル</h1><p>テキストのみ</p>")
        result = semantic_html.run(make_target(html=html))
        assert result.score == 100

    def test_all_images_have_alt_no_deduction(self):
        """全画像に alt があれば減点なし。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body=(
                "<h1>タイトル</h1>"
                '<img src="a.png" alt="画像A">'
                '<img src="b.png" alt="画像B">'
                '<img src="c.png" alt="画像C">'
            ),
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 100

    def test_only_og_title_missing_no_deduction(self):
        """og:description だけある場合（og:title のみ欠落）は OGP の -10点なし。"""
        head = (
            '<meta name="description" content="説明">'
            '<meta property="og:description" content="OGP説明">'
        )
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        # OGP不完全は INFO 止まりで減点しない
        assert result.score == 100

    def test_only_og_desc_missing_no_deduction(self):
        """og:title だけある場合（og:description のみ欠落）は OGP の -10点なし。"""
        head = (
            '<meta name="description" content="説明">'
            '<meta property="og:title" content="タイトル">'
        )
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        assert result.score == 100


# ===========================================================================
# 問題検出系: 各診断項目が正しく検出されるケース
# ===========================================================================


class TestH1Duplicate:
    """h1 重複: -15点 / WARNING。"""

    def test_two_h1_deducts_15(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h1>タイトル1</h1><h1>タイトル2</h1>",
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 85  # 100 - 15
        assert any(f.severity == Severity.WARNING for f in result.findings)

    def test_two_h1_finding_message_contains_count(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h1>A</h1><h1>B</h1>",
        )
        result = semantic_html.run(make_target(html=html))
        assert any("2" in f.message for f in result.findings)

    def test_three_h1_deducts_15_only_once(self):
        """h1 が3つあっても -15点（重複1回分）のみ。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h1>A</h1><h1>B</h1><h1>C</h1>",
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 85


class TestH1Missing:
    """h1 不在: -15点 / WARNING（要件上は「h1 重複 -15点」と同じ減点)。"""

    def test_no_h1_deducts_15(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h2>サブタイトル</h2><p>本文</p>",
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 85

    def test_no_h1_finding_mentions_h1(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h2>サブタイトル</h2>",
        )
        result = semantic_html.run(make_target(html=html))
        assert any("h1" in f.message for f in result.findings)

    def test_no_h1_has_recommendation(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h2>サブタイトル</h2>",
        )
        result = semantic_html.run(make_target(html=html))
        assert len(result.recommendations) >= 1


class TestHeadingSkip:
    """見出しスキップ: -20点 / CRITICAL。"""

    def test_h1_to_h3_skip_deducts_20(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h1>タイトル</h1><h3>サブ</h3>",
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 80  # 100 - 20

    def test_h1_to_h3_skip_is_critical(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h1>タイトル</h1><h3>サブ</h3>",
        )
        result = semantic_html.run(make_target(html=html))
        assert any(f.severity == Severity.CRITICAL for f in result.findings)

    def test_h1_to_h3_finding_message_shows_pair(self):
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h1>A</h1><h3>B</h3>",
        )
        result = semantic_html.run(make_target(html=html))
        skip_finding = next(
            (f for f in result.findings if "スキップ" in f.message), None
        )
        assert skip_finding is not None
        assert "h1" in skip_finding.message or "h3" in skip_finding.message

    def test_decrease_level_not_skip(self):
        """レベルが下がる方向（h3→h1）はスキップではなく許容。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body="<h1>A</h1><h2>B</h2><h3>C</h3><h1>D</h1>",
        )
        result = semantic_html.run(make_target(html=html))
        # スキップの CRITICAL が出ないこと
        skip_criticals = [
            f for f in result.findings
            if f.severity == Severity.CRITICAL and "スキップ" in f.message
        ]
        assert len(skip_criticals) == 0


class TestImgAlt:
    """img alt 欠落。"""

    def test_all_images_missing_alt_deducts_25_critical(self):
        """全画像 alt 無し: -25点 CRITICAL。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body=(
                "<h1>タイトル</h1>"
                '<img src="a.png">'
                '<img src="b.png">'
            ),
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 75  # 100 - 25
        assert any(f.severity == Severity.CRITICAL for f in result.findings)

    def test_majority_missing_alt_deducts_15_warning(self):
        """50%超 alt 無し: -15点 WARNING。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body=(
                "<h1>タイトル</h1>"
                '<img src="a.png">'         # alt 無し
                '<img src="b.png">'         # alt 無し
                '<img src="c.png" alt="C">' # alt あり
            ),
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 85  # 100 - 15
        assert any(f.severity == Severity.WARNING for f in result.findings)

    def test_minority_missing_alt_is_info_no_deduction(self):
        """50%以下 alt 無し: INFO のみ、減点なし。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body=(
                "<h1>タイトル</h1>"
                '<img src="a.png" alt="A">'
                '<img src="b.png" alt="B">'
                '<img src="c.png">'  # 1/3 = 33% → INFO のみ
            ),
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 100
        info_findings = [f for f in result.findings if f.severity == Severity.INFO]
        assert len(info_findings) >= 1


class TestMetaDescription:
    """meta description 不在: -15点 / WARNING。"""

    def test_missing_meta_description_deducts_15(self):
        head = '<meta property="og:title" content="T"><meta property="og:description" content="D">'
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        assert result.score == 85  # 100 - 15

    def test_missing_meta_description_is_warning(self):
        head = '<meta property="og:title" content="T"><meta property="og:description" content="D">'
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        assert any(
            f.severity == Severity.WARNING and "description" in f.message
            for f in result.findings
        )

    def test_meta_description_empty_content_deducts(self):
        """content が空文字列の meta description は「不在」扱い → -15点のみ。"""
        # OGP は両方揃えて OGP 減点(-10)が発生しないようにする
        head = (
            '<meta name="description" content="">'
            '<meta property="og:title" content="タイトル">'
            '<meta property="og:description" content="説明">'
        )
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        assert result.score == 85


class TestOGP:
    """OGP 両方不在: -10点 / WARNING。"""

    def test_both_ogp_missing_deducts_10(self):
        head = '<meta name="description" content="説明">'
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        assert result.score == 90  # 100 - 10

    def test_both_ogp_missing_is_warning(self):
        head = '<meta name="description" content="説明">'
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        assert any(
            f.severity == Severity.WARNING and "OGP" in f.message
            for f in result.findings
        )

    def test_ogp_empty_content_treated_as_missing(self):
        """OGP タグが存在しても content が空なら両方不在扱い → -10点。"""
        head = (
            '<meta name="description" content="説明">'
            '<meta property="og:title" content="">'
            '<meta property="og:description" content="">'
        )
        html = _page(head_extra=head, body="<h1>タイトル</h1>")
        result = semantic_html.run(make_target(html=html))
        assert result.score == 90


# ===========================================================================
# 複数問題の組み合わせ: 減点が積み上がること
# ===========================================================================


class TestCombinedDeductions:
    """複数の問題が同時にある場合、減点が正しく加算されること。"""

    def test_h1_duplicate_and_no_meta_deducts_30(self):
        """h1 重複(-15) + meta description 不在(-15) = -30点。"""
        head = (
            '<meta property="og:title" content="T">'
            '<meta property="og:description" content="D">'
        )
        html = _page(
            head_extra=head,
            body="<h1>A</h1><h1>B</h1>",
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 70  # 100 - 15 - 15

    def test_heading_skip_and_all_alt_missing_deducts_45(self):
        """見出しスキップ(-20) + 全画像 alt 無し(-25) = -45点。"""
        html = _page(
            head_extra=_HEAD_FULL,
            body=(
                "<h1>タイトル</h1>"
                "<h3>スキップ</h3>"
                '<img src="a.png">'
                '<img src="b.png">'
            ),
        )
        result = semantic_html.run(make_target(html=html))
        assert result.score == 55  # 100 - 20 - 25

    def test_all_issues_score_does_not_go_below_zero(self):
        """全問題が重なってもスコアは 0 以下にならない。"""
        head = ""  # meta description も OGP も無し
        html = _page(
            head_extra=head,
            body=(
                # h1 重複(-15)
                "<h1>A</h1><h1>B</h1>"
                # 見出しスキップ(-20): h1→h3
                "<h3>C</h3>"
                # 全画像 alt 無し(-25)
                '<img src="a.png">'
                '<img src="b.png">'
                # meta description 不在(-15) + OGP 両方不在(-10)
            ),
        )
        result = semantic_html.run(make_target(html=html))
        # 最悪: 100 - 15 - 20 - 25 - 15 - 10 = 15点
        # (h1重複とh1欠落は排他: ここでは h1重複 -15点)
        assert result.score >= 0
        assert isinstance(result.score, int)

    def test_all_issues_multiple_findings_returned(self):
        """複数問題があるとき findings も複数返ること。"""
        head = ""
        html = _page(
            head_extra=head,
            body="<h1>A</h1><h1>B</h1><h3>C</h3><img src='x.png'>",
        )
        result = semantic_html.run(make_target(html=html))
        assert len(result.findings) >= 3

    def test_multiple_issues_multiple_recommendations(self):
        """複数問題があるとき recommendations も複数返ること。"""
        head = ""
        html = _page(
            head_extra=head,
            body="<h1>A</h1><h1>B</h1><img src='x.png'>",
        )
        result = semantic_html.run(make_target(html=html))
        assert len(result.recommendations) >= 2


# ===========================================================================
# 壊れた入力: 空HTML・巨大HTML・文字化け相当
# ===========================================================================


class TestBrokenInput:
    """壊れた入力でもクラッシュせず CheckResult を返すこと。"""

    def test_empty_html_returns_result_without_crash(self):
        """完全に空の HTML 文字列でもクラッシュしない。"""
        result = semantic_html.run(make_target(html=""))
        assert result is not None
        assert result.check_id == "semantic_html"
        assert 0 <= result.score <= 100

    def test_empty_html_deducts_for_missing_elements(self):
        """空HTMLは h1 不在 + meta description 不在 + OGP 不在 で減点。"""
        result = semantic_html.run(make_target(html=""))
        # 最低でも h1 不在(-15) + meta description(-15) + OGP(-10) = -40点
        assert result.score <= 60

    def test_very_large_html_returns_within_reasonable_time(self):
        """巨大HTML（約100KB）でもクラッシュせず結果を返す。"""
        # 繰り返しタグで約100KBのHTMLを生成
        items = "\n".join(
            f'<p>段落 {i}: これはサンプルの本文テキストです。AIへの可読性を確認します。</p>'
            for i in range(1000)
        )
        big_body = f"<h1>大きなページ</h1>{items}"
        html = _page(head_extra=_HEAD_FULL, body=big_body)
        result = semantic_html.run(make_target(html=html))
        assert result is not None
        assert 0 <= result.score <= 100

    def test_mojibake_like_input_does_not_crash(self):
        """文字化け相当のバイト列を含む文字列でもクラッシュしない。"""
        # Python str として渡す（実際の文字化けはfetchレイヤーで処理されるが
        # TargetSite.html は str なので代替として制御文字・Replacement Characterを使う）
        garbled = "�\x00\x01\x02" * 100  # U+FFFD = Replacement Character
        html = f"<html><head></head><body><h1>OK</h1>{garbled}</body></html>"
        result = semantic_html.run(make_target(html=html))
        assert result is not None
        assert 0 <= result.score <= 100

    def test_no_head_tag_does_not_crash(self):
        """`<head>` タグが存在しないHTMLでもクラッシュしない。"""
        html = "<html><body><h1>タイトル</h1><p>本文</p></body></html>"
        result = semantic_html.run(make_target(html=html))
        assert result is not None
        assert 0 <= result.score <= 100

    def test_html_with_only_whitespace_does_not_crash(self):
        """空白・改行のみのHTMLでもクラッシュしない。"""
        result = semantic_html.run(make_target(html="   \n\t\n   "))
        assert result is not None
        assert 0 <= result.score <= 100


# ===========================================================================
# CheckResult 構造の検証
# ===========================================================================


class TestResultStructure:
    """run() が返す CheckResult の構造が仕様通りであること。"""

    def test_check_id_is_semantic_html(self):
        result = semantic_html.run(make_target(html=_page()))
        assert result.check_id == "semantic_html"

    def test_title_is_non_empty_string(self):
        result = semantic_html.run(make_target(html=_page()))
        assert isinstance(result.title, str)
        assert len(result.title) > 0

    def test_score_is_int_in_range(self):
        result = semantic_html.run(make_target(html=_page()))
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100

    def test_skipped_is_false_for_normal_input(self):
        result = semantic_html.run(make_target(html=_page()))
        assert result.skipped is False

    def test_findings_is_list(self):
        result = semantic_html.run(make_target(html=_page()))
        assert isinstance(result.findings, list)

    def test_recommendations_is_list(self):
        result = semantic_html.run(make_target(html=_page()))
        assert isinstance(result.recommendations, list)
