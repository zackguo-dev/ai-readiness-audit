"""診断結果を日本語Markdownレポートに整形する。

読者は技術者でない中小企業のマーケ担当者。誠実性ルール(効果を断定しない)を守る。
総合スコアは各項目の WEIGHT による加重平均(スキップ項目は除外)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..checks.base import CheckResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_EFFORT_LABEL = {
    "self": "自分でできる（無料）",
    "vendor": "制作会社に依頼",
}


def _overall_score(results: list[CheckResult], weights: dict[str, float]) -> int:
    scored = [r for r in results if not r.skipped]
    if not scored:
        return 0
    total_w = sum(weights.get(r.check_id, 1.0) for r in scored)
    if total_w == 0:
        return 0
    s = sum(r.score * weights.get(r.check_id, 1.0) for r in scored)
    return round(s / total_w)


def _overall_label(score: int) -> str:
    if score >= 80:
        return "良好"
    if score >= 50:
        return "要改善"
    return "重大"


def _top_improvements(results: list[CheckResult], limit: int = 3):
    """全項目の改善提案を優先度順に集約して上位を返す。"""
    recs = [rec for r in results for rec in r.recommendations]
    recs.sort(key=lambda r: r.priority, reverse=True)
    return recs[:limit]


def _build_context(url: str, results: list[CheckResult], weights, fetched_at):
    overall = _overall_score(results, weights)
    checks_ctx = []
    for r in results:
        checks_ctx.append(
            {
                "title": r.title,
                "score": r.score,
                "label": r.label,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
                "findings": r.findings,
                "self_recs": [x for x in r.recommendations if x.effort == "self"],
                "vendor_recs": [x for x in r.recommendations if x.effort == "vendor"],
            }
        )
    top = [
        {
            "text": rec.text,
            "effort_label": _EFFORT_LABEL.get(rec.effort, rec.effort),
            "cost_hint": rec.cost_hint,
        }
        for rec in _top_improvements(results)
    ]
    return {
        "url": url,
        "fetched_at": fetched_at.strftime("%Y-%m-%d %H:%M UTC"),
        "overall_score": overall,
        "overall_label": _overall_label(overall),
        "top_improvements": top,
        "checks": checks_ctx,
        "effort_label": _EFFORT_LABEL,
        "check_count": len(results),
    }


def render_report(
    url: str,
    results: list[CheckResult],
    weights: dict[str, float],
    *,
    fetched_at: datetime | None = None,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.md.j2")
    ctx = _build_context(
        url, results, weights, fetched_at or datetime.now(timezone.utc)
    )
    return template.render(**ctx)
