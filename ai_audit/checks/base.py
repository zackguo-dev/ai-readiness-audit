"""checks 共通基盤 — 全診断モジュールが返す CheckResult とその構成要素。

各checkモジュールは以下を公開する:
- CHECK_ID:  str       機械可読ID(例 "bot_access")
- TITLE:     str       日本語見出し
- WEIGHT:    float     総合スコアでの重み(根拠はモジュール冒頭コメントに明記)
- run(target: TargetSite) -> CheckResult   共通IF(これを厳守。独自IFを発明しない)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    """所見の深刻度。レポートでの並び順・アイコンに使う。"""

    INFO = 0
    WARNING = 1
    CRITICAL = 2


@dataclass
class Finding:
    """診断で分かった事実1件(日本語・非技術者にも読める文）。"""

    severity: Severity
    message: str
    detail: str = ""


@dataclass
class Recommendation:
    """改善提案1件。effort で「自分でできる/制作会社に依頼」を区分する。"""

    text: str
    effort: str  # "self"(自分でできる・無料) | "vendor"(制作会社に依頼)
    cost_hint: str = ""  # effort=="vendor" のとき費用目安
    priority: int = 0  # 高いほど優先(総合の「効果が大きい改善3つ」抽出に使用)


@dataclass
class CheckResult:
    """1つの診断項目の結果。score は 0-100 に正規化。"""

    check_id: str
    title: str
    score: int  # 0-100
    findings: list[Finding] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    skipped: bool = False  # 環境要因で検証不可だった場合(graceful degradation)
    skip_reason: str = ""

    @property
    def label(self) -> str:
        """スコア帯のざっくり評価ラベル。"""
        if self.skipped:
            return "検証不可"
        if self.score >= 80:
            return "良好"
        if self.score >= 50:
            return "要改善"
        return "重大"
