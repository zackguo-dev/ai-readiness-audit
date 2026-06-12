"""llms_txt — llms.txt / llms-full.txt の存在とフォーマット妥当性の診断。

誠実性ルール(事業の差別化軸・絶対):
- llms.txt は主要AIクローラーがほぼ参照しておらず、現時点で効果は限定的。
- よって「不在」を重大な可読性欠陥として扱わない。低コストな将来投資として
  穏やかに推奨するに留める。「必ず引用される」等の断定はしない。

スコアリング根拠(顧客に説明できること):
- 有効なllms.txtあり = 100(将来投資として整っている)
- あるが形式不備     = 60(意図は良いが体裁が崩れている)
- 不在               = 50(効果が限定的なため、不在でも大きく減点しない)
  ※この項目は総合スコアでの重み(WEIGHT)を小さくして影響を抑える。
"""

from __future__ import annotations

from ..target import TargetSite
from .base import CheckResult, Finding, Recommendation, Severity

CHECK_ID = "llms_txt"
TITLE = "llms.txt の整備状況"
WEIGHT = 0.5  # 効果が限定的なため総合への影響は小さく


def _looks_valid(text: str) -> tuple[bool, list[str]]:
    """llms.txt の最低限のフォーマット妥当性を判定。

    llms.txt 仕様の中核: 先頭に H1 タイトル、本文にリンク(- [name](url))が1つ以上。
    返り値: (妥当か, 問題点の説明リスト)
    """
    problems: list[str] = []
    lines = [ln.rstrip() for ln in text.splitlines()]
    nonblank = [ln for ln in lines if ln.strip()]

    has_h1 = any(ln.lstrip().startswith("# ") for ln in nonblank[:5])
    if not has_h1:
        problems.append("先頭付近に H1 見出し(# タイトル)がありません")

    has_link = any("](" in ln and "[" in ln for ln in nonblank)
    if not has_link:
        problems.append("リンク(- [名前](URL) 形式)が1つもありません")

    return (not problems, problems)


def run(target: TargetSite) -> CheckResult:
    findings: list[Finding] = []
    recommendations: list[Recommendation] = []

    if target.llms_txt is None:
        # 不在: 効果限定のため穏当に扱う(誠実性ルール)
        findings.append(
            Finding(
                Severity.INFO,
                "llms.txt は設置されていません",
                "llms.txt(AI向けにサイト構成を案内するファイル)は、現時点で主要AIの"
                "参照は限定的です。設置していなくても大きな問題ではありません。",
            )
        )
        recommendations.append(
            Recommendation(
                "llms.txt の設置を「低コストな将来投資」として検討する"
                "(効果は未知数。今すぐの優先度は高くありません)",
                effort="self",
                priority=20,
            )
        )
        return CheckResult(CHECK_ID, TITLE, 50, findings, recommendations)

    valid, problems = _looks_valid(target.llms_txt)
    if valid:
        findings.append(
            Finding(Severity.INFO, "有効な形式の llms.txt が設置されています")
        )
        if target.llms_full_txt is not None:
            findings.append(
                Finding(Severity.INFO, "llms-full.txt も設置されています")
            )
        return CheckResult(CHECK_ID, TITLE, 100, findings, recommendations)

    # あるが形式不備
    for p in problems:
        findings.append(Finding(Severity.WARNING, f"llms.txt の形式不備: {p}"))
    recommendations.append(
        Recommendation(
            "llms.txt を仕様に沿って整える(先頭にH1タイトル、本文に主要ページへのリンク)",
            effort="self",
            priority=30,
        )
    )
    return CheckResult(CHECK_ID, TITLE, 60, findings, recommendations)
