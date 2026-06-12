"""js_dependency — JavaScript依存度の診断(本診断の本丸)。

AIクローラーの多くはJavaScriptを実行せず、静的HTMLだけを読む。
JSで後から描画されるコンテンツは「人間には見えてもAIには見えない」。
本checkは静的HTML(TargetSiteが取得済み)とPlaywrightレンダリング後の
可視テキスト量を比較し、AIに届いていないコンテンツの割合を測る。

JS依存率 = (レンダリング後テキスト量 - 静的テキスト量) / レンダリング後テキスト量
- 30%超: 警告(コンテンツの3割以上がAIに見えていない)
- 60%超: 重大(コンテンツの大半がAIに見えていない)

スコアリング根拠(顧客に説明できること):
- score = 100 - JS依存率(%)。「AIが読めないテキストの割合を、そのまま100点から
  引く」という最も透明な式。依存率30%なら70点、60%なら40点。
  レポートのラベル帯(80以上=良好/50以上=要改善/50未満=重大)とも整合し、
  依存率20%以下で「良好」、50%超で「重大」帯に入る。

graceful degradation:
- Playwright未導入・ブラウザ未取得・ナビゲーション失敗などの環境要因では
  例外で落とさず skipped=True とし、「動的検証不可」をfindingsに明記する
  (スキップ項目は総合スコアの加重平均から除外される)。

ネットワーク方針: 静的HTMLは再フェッチしない。Playwrightでの取得は1回のみ。
UAは既存TargetSiteのDEFAULT_UAに揃える。タイムアウト明示。
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from ..target import DEFAULT_UA, TargetSite
from .base import CheckResult, Finding, Recommendation, Severity

CHECK_ID = "js_dependency"
TITLE = "JavaScript依存度(AIが読めるテキスト量)"
WEIGHT = 2.0  # 「HTMLが実際にAIに読めるか」の中核指標。bot_accessと並ぶ最重要項目

# 警告・重大のしきい値(仕様で固定)
WARN_RATIO = 0.30
CRITICAL_RATIO = 0.60

# Playwrightのナビゲーションタイムアウト(ミリ秒)。明示必須。
NAV_TIMEOUT_MS = 20_000

# 可視テキストに含めないタグ(実行コード・スタイル・非表示テンプレート類)
_INVISIBLE_TAGS = ["script", "style", "noscript", "template", "svg", "head"]


# --- テキスト抽出(純粋関数・テスト対象) --------------------------------------


def extract_visible_text(html: str) -> str:
    """HTMLから可視テキストを抽出する(script/style等は除外)。

    注意: strip_tags は解析木を破壊的に変更するため、target.tree(共有キャッシュ)は
    使わず、必ずこの場で新しい解析木を作る。
    """
    tree = HTMLParser(html or "")
    tree.strip_tags(_INVISIBLE_TAGS)
    node = tree.body or tree.root
    if node is None:
        return ""
    return node.text(separator=" ")


def text_volume(text: str) -> int:
    """テキスト量 = 空白類を除いた文字数。

    日本語は単語分割が曖昧なため、語数ではなく文字数で比較する。
    空白を除くのは、整形差(改行・インデント)で量が揺れないようにするため。
    """
    return len(re.sub(r"\s+", "", text))


# --- Playwrightレンダリング(遅延import。テストでは monkeypatch する) -----------


def render_html(
    url: str, *, user_agent: str = DEFAULT_UA, timeout_ms: int = NAV_TIMEOUT_MS
) -> str:
    """ChromiumでページをレンダリングしてJS実行後のHTMLを返す(取得は1回のみ)。

    playwrightは遅延import: 未導入環境でもツール全体がimportエラーで
    落ちないようにする(呼び出し側でImportError含む例外を処理)。
    """
    from playwright.sync_api import (  # noqa: PLC0415 - 意図的な遅延import
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=user_agent)
            try:
                # networkidle: JS描画完了を待つ。常時通信するサイトでは到達しない
                # ことがあるため、タイムアウトしてもその時点のDOMで比較を続行する。
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                pass
            return page.content()
        finally:
            browser.close()


# --- 共通IF ------------------------------------------------------------------


def run(target: TargetSite) -> CheckResult:
    static_vol = text_volume(extract_visible_text(target.html))

    # 環境要因(未導入・ブラウザ未取得・起動失敗・通信失敗)はすべて検証不可として
    # graceful degradation。診断全体は止めない。
    try:
        rendered_html = render_html(target.final_url or target.url)
    except Exception as exc:  # noqa: BLE001 - 失敗理由を問わずスキップ扱いにする
        return _skipped_result(exc)

    rendered_vol = text_volume(extract_visible_text(rendered_html))
    if rendered_vol == 0:
        # 描画結果が空 = レンダリング自体が機能していない可能性が高く、
        # 比較すると誤って「依存度0%」になるため検証不可として扱う。
        return _skipped_result(
            RuntimeError("レンダリング後のページからテキストを取得できませんでした")
        )

    # JS依存率。静的の方が多い場合(JSが文言を削るレアケース)は0%に丸める。
    ratio = max(0.0, (rendered_vol - static_vol) / rendered_vol)
    pct = round(ratio * 100)
    score = max(0, 100 - pct)  # 根拠: AIが読めないテキストの割合をそのまま減点

    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    detail = (
        f"JavaScript実行前のテキスト量: {static_vol:,}文字 / "
        f"実行後: {rendered_vol:,}文字(JS依存率 {pct}%)。"
        "多くのAIはJavaScriptを実行しないため、実行後にしか現れない部分は"
        "AIに読まれません。"
    )

    if ratio > CRITICAL_RATIO:
        findings.append(
            Finding(
                Severity.CRITICAL,
                f"コンテンツの約{pct}%がJavaScript実行後にしか表示されません",
                detail,
            )
        )
        recommendations.append(
            Recommendation(
                "サーバーサイドレンダリング(SSR)や事前レンダリングを導入し、"
                "ページの文章をJavaScript無しでも読める形で配信する",
                effort="vendor",
                cost_hint="サイトの作りによるが10〜30万円程度が目安",
                priority=88,  # bot_accessのブロック(90)に次ぐ優先度
            )
        )
    elif ratio > WARN_RATIO:
        findings.append(
            Finding(
                Severity.WARNING,
                f"コンテンツの約{pct}%がJavaScript実行後にしか表示されません",
                detail,
            )
        )
        recommendations.append(
            Recommendation(
                "会社概要・サービス説明・FAQなど重要な文章が、JavaScriptを切った"
                "状態でも表示されるか確認し、HTMLに直接含める構成に見直す",
                effort="vendor",
                cost_hint="対象ページ数によるが数万円〜",
                priority=60,
            )
        )
    else:
        findings.append(
            Finding(
                Severity.INFO,
                f"主要なコンテンツは静的HTMLに含まれています(JS依存率 {pct}%)",
                detail,
            )
        )

    return CheckResult(CHECK_ID, TITLE, score, findings, recommendations)


def _skipped_result(exc: Exception) -> CheckResult:
    """動的検証不可(環境要因)の結果。総合スコアの計算からは除外される。"""
    reason = f"ブラウザでの動的検証を実行できませんでした({type(exc).__name__})"
    return CheckResult(
        check_id=CHECK_ID,
        title=TITLE,
        score=0,
        findings=[
            Finding(
                Severity.INFO,
                "動的検証不可: JavaScript依存度を測定できませんでした",
                "診断ツール側の環境要因(ブラウザ未導入など)によるもので、"
                "対象サイト側の問題ではありません。この項目は総合スコアの"
                "計算から除外しています。",
            )
        ],
        skipped=True,
        skip_reason=reason,
    )
