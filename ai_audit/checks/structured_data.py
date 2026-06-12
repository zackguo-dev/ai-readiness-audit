"""structured_data — JSON-LD 構造化データの診断。

AIはHTMLのテキストだけでなく、構造化データ(JSON-LD)から
エンティティ情報を取得する。Schema.orgの主要タイプが正しく実装されているか診断する。

診断内容:
1. JSON-LD ブロックの有無と解析可能性
2. Schema.orgタイプの列挙(@type)
3. 主要タイプ別の必須プロパティ欠落チェック:
   - Organization: name, url
   - Article:       headline, author, datePublished
   - Product:       name, description, offers
   - FAQPage:       mainEntity(Question/acceptedAnswer)

スコアリング根拠(顧客に説明できること):
- 基準点: JSON-LDが1件以上あれば60点(「ある」「ない」が最大の差)
- 各タイプで必須プロパティが揃っていれば追加点:
    - 1タイプ目: +20点、2タイプ目以降: +10点ずつ(上限100)
  → 「何も無い」=0点、「あるが不完全」=60点台、「主要タイプが揃っている」=80点以上。
- JSON-LDが全て解析失敗=「壊れたデータ」として0点(Noneより悪い)。
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..target import TargetSite
from .base import CheckResult, Finding, Recommendation, Severity

CHECK_ID = "structured_data"
TITLE = "構造化データ(JSON-LD / Schema.org)"
WEIGHT = 1.5  # SEO/GEO双方に効くが、js_dependencyほど致命的ではない

# 各Schema.orgタイプで「これが無いと意味をなさない」必須プロパティ。
# 根拠: Schema.org公式仕様の recommended/required + Googleリッチリザルト要件。
_REQUIRED_PROPS: dict[str, list[str]] = {
    "Organization": ["name", "url"],
    "Article":      ["headline", "author", "datePublished"],
    "Product":      ["name", "description", "offers"],
    "FAQPage":      ["mainEntity"],
}

# Organization の別名タイプ(LocalBusiness 等は Organization のサブタイプ)
_ORG_SUBTYPES = {
    "LocalBusiness", "Corporation", "EducationalOrganization",
    "GovernmentOrganization", "MedicalOrganization", "NGO",
    "SportsOrganization", "WorkersUnion",
}


def _extract_jsonld_blocks(html: str) -> list[dict[str, Any]]:
    """HTML から <script type="application/ld+json"> を全件抽出し、
    JSON として解析できたオブジェクト(dict または @graph 展開後のリスト)だけ返す。

    - @graph を持つ場合は展開して個別オブジェクトとして扱う。
    - 解析失敗ブロックは _parse_errors カウントのために None を混ぜる(呼び元で処理)。
    """
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    results: list[dict[str, Any] | None] = []
    for m in pattern.finditer(html):
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            results.append(None)  # 解析失敗マーカー
            continue
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    results.append(item)
        elif isinstance(obj, dict):
            if "@graph" in obj and isinstance(obj["@graph"], list):
                for item in obj["@graph"]:
                    if isinstance(item, dict):
                        results.append(item)
            else:
                results.append(obj)
    return results  # type: ignore[return-value]


def _normalize_type(raw_type: Any) -> list[str]:
    """@type の値を文字列リストに正規化する(単一文字列・リスト・URL形式を扱う)。"""
    if isinstance(raw_type, str):
        types = [raw_type]
    elif isinstance(raw_type, list):
        types = [t for t in raw_type if isinstance(t, str)]
    else:
        return []
    # "https://schema.org/Article" → "Article" に正規化
    return [t.split("/")[-1] for t in types]


def _check_required_props(obj: dict[str, Any], schema_type: str) -> list[str]:
    """必須プロパティのうち欠落しているものを返す。

    正規化: Organization のサブタイプは Organization として扱う。
    """
    normalized = "Organization" if schema_type in _ORG_SUBTYPES else schema_type
    required = _REQUIRED_PROPS.get(normalized, [])
    return [p for p in required if p not in obj]


# --- 共通IF ------------------------------------------------------------------


def run(target: TargetSite) -> CheckResult:
    raw_blocks = _extract_jsonld_blocks(target.html)

    # None = 解析失敗ブロック を分離
    parse_errors = sum(1 for b in raw_blocks if b is None)
    blocks: list[dict[str, Any]] = [b for b in raw_blocks if b is not None]

    findings: list[Finding] = []
    recommendations: list[Recommendation] = []

    # --- JSON-LD が1件も無い ---
    if not blocks and parse_errors == 0:
        findings.append(
            Finding(
                Severity.WARNING,
                "JSON-LD 形式の構造化データが見つかりませんでした",
                "Schema.org の構造化データは、AIがサイトの「組織名」「記事の著者」"
                "「商品情報」などをエンティティとして正確に把握するために使われます。"
                "未実装だと、AIが文脈から推測するしかなく、情報の正確さが下がります。",
            )
        )
        recommendations.append(
            Recommendation(
                "Organization または Article の JSON-LD を <head> 内に追加する。"
                "Google の「構造化データ マークアップ支援ツール」で雛形を生成できます",
                effort="self",
                priority=70,
            )
        )
        return CheckResult(CHECK_ID, TITLE, 0, findings, recommendations)

    # --- 解析失敗ブロックがある(JSONが壊れている) ---
    if parse_errors > 0:
        findings.append(
            Finding(
                Severity.CRITICAL,
                f"JSON-LD ブロックが {parse_errors} 件、構文エラーで読み取れません",
                "JSON の記述に誤り(閉じカッコ忘れ・不正なエスケープ等)があります。"
                "AIはこのデータを完全に無視します。",
            )
        )
        recommendations.append(
            Recommendation(
                "Google Search Console の「リッチリザルト テスト」でJSON-LDの構文エラーを修正する",
                effort="self",
                priority=85,
            )
        )

    # --- タイプ別に必須プロパティを確認 ---
    found_types: list[str] = []
    missing_per_type: dict[str, list[str]] = {}

    for obj in blocks:
        raw_type = obj.get("@type")
        types = _normalize_type(raw_type)
        for t in types:
            if t not in found_types:
                found_types.append(t)
            missing = _check_required_props(obj, t)
            if missing:
                # 同じタイプが複数ブロックにある場合は欠落が少ない方(良い方)を採用
                if t not in missing_per_type or len(missing) < len(missing_per_type[t]):
                    missing_per_type[t] = missing

    # タイプが全く宣言されていないブロックのみの場合
    if not found_types:
        findings.append(
            Finding(
                Severity.WARNING,
                "JSON-LD ブロックはありますが @type が宣言されていません",
                "Schema.org の @type が無いと、AIはデータの意味を解釈できません。",
            )
        )

    # 検出タイプを INFO で列挙
    if found_types:
        findings.append(
            Finding(
                Severity.INFO,
                f"検出された Schema.org タイプ: {', '.join(found_types)}",
            )
        )

    # 必須プロパティ欠落を報告
    for schema_type, missing in missing_per_type.items():
        findings.append(
            Finding(
                Severity.WARNING,
                f"{schema_type}: 必須プロパティ {', '.join(missing)} が見つかりません",
                f"Schema.org の {schema_type} タイプには {', '.join(missing)} が"
                "必要です。これらが無いとAIが情報を正確に構造化できません。",
            )
        )
        recommendations.append(
            Recommendation(
                f"JSON-LD の {schema_type} に {', '.join(missing)} プロパティを追加する",
                effort="self",
                priority=65,
            )
        )

    # --- スコア計算 ---
    # JSON-LDが1件以上ある = 60点ベース
    if parse_errors > 0 and not blocks:
        score = 0
    else:
        score = 60
        # 必須プロパティが揃っているタイプ数でボーナス加算
        complete_types = [t for t in found_types if t not in missing_per_type]
        for i, _ in enumerate(complete_types):
            score += 20 if i == 0 else 10
        score = min(100, score)
        # 解析エラーがある場合はペナルティ
        if parse_errors > 0:
            score = max(0, score - 20)

    return CheckResult(CHECK_ID, TITLE, score, findings, recommendations)
