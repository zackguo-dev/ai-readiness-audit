"""semantic_html — セマンティックHTMLの診断。

AIクローラーはHTMLの構造からコンテンツの意味を読み取る。
見出し階層・alt属性・メタ情報が正しく実装されているか診断する。

診断内容:
1. 見出し階層 — h1 の重複（2個以上で WARNING）、レベルスキップ（CRITICAL）
2. img の alt 属性 — alt 無し比率。50%超で WARNING、全て無しで CRITICAL
3. meta description — 不在なら WARNING
4. OGP（og:title / og:description） — 両方不在なら WARNING

スコアリング根拠（顧客に説明できること）:
- 基準点 100 点からの減点方式。下限 0。
- h1 重複: -15点
    h1 はページの主題を示す唯一の見出し。複数あるとAIが
    「このページは何のページか」を誤認識する可能性がある。
- 見出しスキップ: -20点（CRITICAL相当）
    h1→h3 のような飛ばしは文書構造が壊れているとAIに判断される。
    コンテンツの論理的なまとまりが伝わらなくなる。
- alt 無し画像 50%超: -15点
    画像の内容はAIが読めない。altがあることで、画像の代わりに
    テキストでコンテキストを補える。半数以上が欠落は要改善。
- alt 無し画像 100%: -25点（50%超 -15点との累積ではなく独立適用）
    全画像が alt 無しは画像を「装飾のみ」と宣言しているのと等価。
    情報量の損失が大きい。（50%超と排他: 100%の場合は -25点のみ）
- meta description 不在: -15点
    検索スニペットだけでなく、AIがページ概要を把握する際にも
    meta description は参照される。不在だと要約精度が下がる。
- OGP 未設定（og:title も og:description も無し）: -10点
    SNS共有時の表示に使われるが、AIがページを引用するときの
    タイトル・説明としても使われる。低コストで効果があるため
    実装を推奨するが、他項目ほど致命的ではない（-10点）。
"""

from __future__ import annotations

from ..target import TargetSite
from .base import CheckResult, Finding, Recommendation, Severity

CHECK_ID = "semantic_html"
TITLE = "セマンティックHTML"
# 見出し・alt・メタ情報はAI可読性の基礎。js_dependency・structured_data と同等の重み。
WEIGHT = 1.5


def _check_headings(tree) -> tuple[list[Finding], list[Recommendation], int]:
    """見出し階層の問題を検査し、(findings, recommendations, 減点額) を返す。"""
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    deduction = 0

    h1_nodes = tree.css("h1")
    h1_count = len(h1_nodes)

    # h1 重複チェック: -15点
    if h1_count == 0:
        findings.append(
            Finding(
                Severity.WARNING,
                "ページに h1 見出しがありません",
                "h1 はページの主題を示す最重要見出しです。AIはh1を最初に参照して"
                "ページのトピックを把握します。必ず1つ設置してください。",
            )
        )
        deduction += 15
        recommendations.append(
            Recommendation(
                "ページのメインタイトルを <h1> タグで囲む",
                effort="self",
                priority=75,
            )
        )
    elif h1_count > 1:
        findings.append(
            Finding(
                Severity.WARNING,
                f"h1 見出しが {h1_count} 個あります（1個が正しい）",
                "h1 はページに1つだけ設置するのがHTMLの仕様です。複数あると"
                "AIが「このページの主題は何か」を誤認識します。",
            )
        )
        deduction += 15
        recommendations.append(
            Recommendation(
                f"h1 を1つにまとめ、残り {h1_count - 1} 個は h2 以下に変更する",
                effort="self",
                priority=70,
            )
        )

    # 見出しスキップチェック: -20点
    # 全見出し(h1〜h6)を出現順に取得し、レベルが2以上飛んでいる箇所を検出する。
    all_headings = tree.css("h1, h2, h3, h4, h5, h6")
    prev_level = 0
    skipped_pairs: list[str] = []
    for node in all_headings:
        tag = node.tag.lower()  # "h1" / "h2" ...
        level = int(tag[1])
        # レベルが増加方向に2以上飛んでいる場合がスキップ（例: h1→h3）。
        # 減少方向（h3→h1）はセクション戻りとして許容する。
        if prev_level > 0 and level > prev_level + 1:
            skipped_pairs.append(f"h{prev_level}→h{level}")
        prev_level = level

    if skipped_pairs:
        examples = ", ".join(dict.fromkeys(skipped_pairs))  # 重複除去・順序保持
        findings.append(
            Finding(
                Severity.CRITICAL,
                f"見出しレベルのスキップが検出されました（{examples}）",
                "見出しは h1→h2→h3 の順に使うのが正しい構造です。レベルを飛ばすと"
                "AIが文書の論理構造を正確に把握できなくなります。",
            )
        )
        deduction += 20
        recommendations.append(
            Recommendation(
                "見出しタグを h1→h2→h3 の順番で使うよう修正する（レベルを飛ばさない）",
                effort="self",
                priority=80,
            )
        )

    return findings, recommendations, deduction


def _check_alt(tree) -> tuple[list[Finding], list[Recommendation], int]:
    """img の alt 属性欠落を検査し、(findings, recommendations, 減点額) を返す。"""
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    deduction = 0

    img_nodes = tree.css("img")
    total = len(img_nodes)

    if total == 0:
        # 画像が1枚もない場合は減点なし・所見なし
        return findings, recommendations, deduction

    # alt が None または空文字列を「欠落」とみなす。
    # alt="" は意図的な装飾画像として許容する実装も存在するが、
    # AIへの情報提供の観点では区別せず欠落として扱う。
    missing = sum(
        1 for n in img_nodes
        if not n.attributes.get("alt")
    )
    ratio = missing / total  # 0.0〜1.0

    if ratio == 1.0:
        # 全て欠落: CRITICAL -25点
        findings.append(
            Finding(
                Severity.CRITICAL,
                f"全ての画像（{total}枚）に alt 属性がありません",
                "alt 属性はAIが画像の内容を理解するための唯一の手段です。"
                "全画像に alt がないと、ページ内の画像コンテンツは全てAIに"
                "見えない状態になります。",
            )
        )
        deduction += 25
        recommendations.append(
            Recommendation(
                f"全 {total} 枚の <img> タグに alt=\"画像の説明\" を追加する",
                effort="self",
                priority=85,
            )
        )
    elif ratio > 0.5:
        # 半数超欠落: WARNING -15点
        findings.append(
            Finding(
                Severity.WARNING,
                f"画像 {total} 枚中 {missing} 枚（{ratio:.0%}）に alt 属性がありません",
                "alt 属性がない画像はAIに内容が伝わりません。半数以上が欠落しており、"
                "ページの情報量がAIに正しく届いていません。",
            )
        )
        deduction += 15
        recommendations.append(
            Recommendation(
                f"alt 無しの {missing} 枚の <img> タグに画像の内容を説明する alt を追加する",
                effort="self",
                priority=70,
            )
        )
    elif missing > 0:
        # 半数以下の欠落: INFO（減点なし・認識させるだけ）
        findings.append(
            Finding(
                Severity.INFO,
                f"画像 {total} 枚中 {missing} 枚に alt 属性がありません",
                "可能であれば全画像に alt を設定することを推奨します。",
            )
        )

    return findings, recommendations, deduction


def _check_meta_description(tree) -> tuple[list[Finding], list[Recommendation], int]:
    """meta description の有無を検査し、(findings, recommendations, 減点額) を返す。"""
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    deduction = 0

    node = tree.css_first('meta[name="description"]')
    has_content = node is not None and bool(
        (node.attributes.get("content") or "").strip()
    )

    if not has_content:
        findings.append(
            Finding(
                Severity.WARNING,
                "meta description が設定されていません",
                "meta description はAIがページ概要を把握する際に参照します。"
                "設定がないと、AIはページ本文から自力で概要を推測するしかなく、"
                "引用時の精度が落ちます。",
            )
        )
        deduction += 15
        recommendations.append(
            Recommendation(
                "<head> 内に <meta name=\"description\" content=\"ページの概要（120〜160文字）\"> を追加する",
                effort="self",
                priority=65,
            )
        )

    return findings, recommendations, deduction


def _check_ogp(tree) -> tuple[list[Finding], list[Recommendation], int]:
    """OGP（og:title / og:description）の有無を検査し、(findings, recommendations, 減点額) を返す。"""
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    deduction = 0

    og_title = tree.css_first('meta[property="og:title"]')
    og_desc = tree.css_first('meta[property="og:description"]')

    has_title = og_title is not None and bool(
        (og_title.attributes.get("content") or "").strip()
    )
    has_desc = og_desc is not None and bool(
        (og_desc.attributes.get("content") or "").strip()
    )

    # og:title も og:description も両方ない場合のみ警告・減点。
    # 片方だけある場合は部分実装として減点しない（実装者の意図を尊重）。
    if not has_title and not has_desc:
        findings.append(
            Finding(
                Severity.WARNING,
                "OGP タグ（og:title / og:description）が設定されていません",
                "OGP タグはSNS共有時の表示に使われますが、AIがページを引用する際の"
                "タイトルや説明としても参照されます。低コストで実装できます。",
            )
        )
        deduction += 10
        recommendations.append(
            Recommendation(
                "<head> 内に og:title・og:description・og:url・og:image を追加する"
                "（CMSのSEOプラグインで自動生成できる場合が多い）",
                effort="self",
                priority=50,
            )
        )
    elif not has_title:
        findings.append(
            Finding(
                Severity.INFO,
                "og:description はありますが og:title がありません",
            )
        )
    elif not has_desc:
        findings.append(
            Finding(
                Severity.INFO,
                "og:title はありますが og:description がありません",
            )
        )

    return findings, recommendations, deduction


# --- 共通IF ------------------------------------------------------------------


def run(target: TargetSite) -> CheckResult:
    tree = target.tree
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []
    total_deduction = 0

    # 各サブチェックを実行して結果を集約する
    for checker in (_check_headings, _check_alt, _check_meta_description, _check_ogp):
        f, r, d = checker(tree)
        findings.extend(f)
        recommendations.extend(r)
        total_deduction += d

    score = max(0, 100 - total_deduction)

    return CheckResult(CHECK_ID, TITLE, score, findings, recommendations)
