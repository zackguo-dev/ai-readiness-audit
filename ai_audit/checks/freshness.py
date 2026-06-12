"""freshness — コンテンツの鮮度・日付情報の診断。

AIクローラーは「いつ書かれた情報か」を判断するために日付マークアップを参照する。
更新日が明示されていないページは古い情報とみなされ、引用されにくくなる。
また sitemap.xml にlastmodを記録することで、クローラーが効率的に更新を検知できる。

診断内容:
1. 公開日・更新日のマークアップ — 以下の優先順で探す:
   - <meta property="article:published_time" content="..."> (OGP)
   - <meta property="article:modified_time" content="...">  (OGP)
   - <time datetime="..."> 要素
   - JSON-LD の datePublished / dateModified
2. sitemap.xml の存在 — HEAD リクエスト 1 回で確認

スコアリング根拠（顧客に説明できること）:
- 基準点 100 点からの減点方式。下限 0。
- 公開日・更新日どちらも見つからない: -30点 (WARNING)
    日付情報がゼロだと、AIはページがいつ書かれたか判断できない。
    古い情報を誤って引用するリスクが高まる。
- 公開日のみで更新日なし: -10点 (INFO)
    公開日があるのは評価できるが、更新日があれば
    「このページは最近もメンテされている」とAIが判断できる。
- sitemap.xml が存在しない: -20点 (WARNING)
    sitemap.xml の <lastmod> はクローラーが再クロールの優先順位を
    決める主要シグナル。存在しないと更新頻度が伝わらない。
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..target import DEFAULT_UA, TargetSite
from .base import CheckResult, Finding, Recommendation, Severity
from .structured_data import _extract_jsonld_blocks

CHECK_ID = "freshness"
TITLE = "コンテンツの鮮度・日付情報"
# 日付マークアップは実装コストが低いわりにAI引用に直結する。
# structured_data と同等の重みとする。
WEIGHT = 1.0


# ---------------------------------------------------------------------------
# サブチェック: HTML 内日付マークアップ
# ---------------------------------------------------------------------------


def _find_date_in_meta(tree) -> tuple[str | None, str | None]:
    """OGP meta タグから公開日・更新日を返す。見つからなければ None。"""
    pub_node = tree.css_first('meta[property="article:published_time"]')
    mod_node = tree.css_first('meta[property="article:modified_time"]')
    pub = pub_node.attributes.get("content") if pub_node is not None else None
    mod = mod_node.attributes.get("content") if mod_node is not None else None
    # 空文字列は「なし」扱い
    return (pub or None), (mod or None)


def _find_date_in_time_element(tree) -> tuple[str | None, str | None]:
    """<time datetime="..."> 要素から公開日・更新日を探す。

    複数の <time> 要素がある場合、最初に見つかった値を公開日、
    2番目を更新日として扱う（多くの CMS がこの順序で出力する）。
    datetime 属性がない <time> は無視する。
    """
    times = [
        node.attributes.get("datetime")
        for node in tree.css("time")
        if node.attributes.get("datetime")
    ]
    pub = times[0] if len(times) >= 1 else None
    mod = times[1] if len(times) >= 2 else None
    return pub, mod


def _find_date_in_jsonld(html: str) -> tuple[str | None, str | None]:
    """JSON-LD から datePublished / dateModified を探す。

    _extract_jsonld_blocks は None（解析失敗）を含む可能性があるが、
    ここでは dict のみを対象にする。最初に見つかった値を採用する。
    """
    raw_blocks = _extract_jsonld_blocks(html)
    blocks: list[dict[str, Any]] = [b for b in raw_blocks if isinstance(b, dict)]

    pub: str | None = None
    mod: str | None = None
    for obj in blocks:
        if pub is None:
            pub = obj.get("datePublished") or None
        if mod is None:
            mod = obj.get("dateModified") or None
        if pub and mod:
            break
    return pub, mod


def _check_date_markup(target: TargetSite) -> tuple[list[Finding], list[Recommendation], int]:
    """公開日・更新日マークアップを検査し、(findings, recommendations, 減点額) を返す。

    優先順位: OGP meta → <time datetime> → JSON-LD
    各ソースで見つかった最初の値を採用する（複数ソースがある場合も減点なし）。
    """
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    deduction = 0

    tree = target.tree
    html = target.html

    # --- OGP meta から取得
    pub, mod = _find_date_in_meta(tree)

    # --- <time datetime> で補完
    if pub is None or mod is None:
        t_pub, t_mod = _find_date_in_time_element(tree)
        pub = pub or t_pub
        mod = mod or t_mod

    # --- JSON-LD で補完
    if pub is None or mod is None:
        j_pub, j_mod = _find_date_in_jsonld(html)
        pub = pub or j_pub
        mod = mod or j_mod

    if pub is None and mod is None:
        # 公開日・更新日どちらも見つからない: -30点
        findings.append(
            Finding(
                Severity.WARNING,
                "公開日・更新日のマークアップが見つかりません",
                "AIはページの日付情報を参照して「情報の新鮮さ」を判断します。"
                "日付マークアップがないと、古い情報とみなされて引用されにくくなります。"
                "article:published_time (OGP)・<time datetime> 要素・"
                "JSON-LD の datePublished のいずれかを設置してください。",
            )
        )
        deduction += 30
        recommendations.append(
            Recommendation(
                "<head> 内に <meta property=\"article:published_time\" content=\"YYYY-MM-DD\"> を追加する"
                "（CMSのSEOプラグインで自動生成できることが多い）",
                effort="self",
                priority=75,
            )
        )
    elif mod is None:
        # 公開日のみ・更新日なし: -10点
        findings.append(
            Finding(
                Severity.INFO,
                f"公開日は設定されています（{pub}）が、更新日のマークアップがありません",
                "更新日があると、AIが「このページは最近もメンテされている」と判断しやすくなります。"
                "article:modified_time (OGP) または JSON-LD の dateModified を追加することを推奨します。",
            )
        )
        deduction += 10
        recommendations.append(
            Recommendation(
                "<head> 内に <meta property=\"article:modified_time\" content=\"YYYY-MM-DD\"> を追加する",
                effort="self",
                priority=45,
            )
        )
    else:
        # 公開日・更新日ともに設定済み: 減点なし
        findings.append(
            Finding(
                Severity.INFO,
                f"公開日（{pub}）・更新日（{mod}）が設定されています",
            )
        )

    return findings, recommendations, deduction


# ---------------------------------------------------------------------------
# サブチェック: sitemap.xml の存在確認
# ---------------------------------------------------------------------------


def _check_sitemap(origin: str) -> bool:
    """origin + "/sitemap.xml" に HEAD リクエストを1回送り、200 なら True を返す。

    - リトライなし・失敗は「存在しない」扱い（診断の遅延を避けるため）。
    - bot_access チェックと同様に例外的なフェッチ（CLAUDE.md 仕様許可済み）。
    """
    url = origin + "/sitemap.xml"
    try:
        r = httpx.head(
            url,
            timeout=5.0,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_UA},
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _check_sitemap_existence(
    target: TargetSite,
) -> tuple[list[Finding], list[Recommendation], int]:
    """sitemap.xml の有無を検査し、(findings, recommendations, 減点額) を返す。"""
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    deduction = 0

    has_sitemap = _check_sitemap(target.origin)

    if has_sitemap:
        findings.append(
            Finding(
                Severity.INFO,
                "sitemap.xml が確認されました",
                "クローラーが更新ページを効率的に発見できます。"
                "<lastmod> タグで更新日時を記録することでさらに効果が高まります。",
            )
        )
    else:
        # sitemap.xml なし: -20点
        findings.append(
            Finding(
                Severity.WARNING,
                "sitemap.xml が見つかりません",
                "sitemap.xml の <lastmod> はクローラーが再クロールの優先順位を決める"
                "主要シグナルです。存在しないと、AIクローラーに更新頻度が伝わりません。",
            )
        )
        deduction += 20
        recommendations.append(
            Recommendation(
                "sitemap.xml を /sitemap.xml に設置し、robots.txt の Sitemap: ディレクティブで場所を明示する"
                "（WordPressなら Yoast SEO / All in One SEO で自動生成できる）",
                effort="self",
                priority=60,
            )
        )

    return findings, recommendations, deduction


# ---------------------------------------------------------------------------
# 共通IF
# ---------------------------------------------------------------------------


def run(target: TargetSite) -> CheckResult:
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    total_deduction = 0

    # サブチェック 1: 日付マークアップ
    f, r, d = _check_date_markup(target)
    findings.extend(f)
    recommendations.extend(r)
    total_deduction += d

    # サブチェック 2: sitemap.xml 存在確認（例外的フェッチ・1回のみ）
    f, r, d = _check_sitemap_existence(target)
    findings.extend(f)
    recommendations.extend(r)
    total_deduction += d

    score = max(0, 100 - total_deduction)

    return CheckResult(CHECK_ID, TITLE, score, findings, recommendations)
