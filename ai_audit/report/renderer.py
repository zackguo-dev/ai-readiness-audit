"""診断結果を日本語レポートに整形する。

HTML レポート(render_html)と Markdown レポート(render_markdown)の2つを提供する。
render_report は render_markdown の後方互換エイリアス。
総合スコアは各項目の WEIGHT による加重平均(スキップ項目は除外)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..checks.base import CheckResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_EFFORT_LABEL = {
    "self": "自分でできる（無料）",
    "vendor": "制作会社に依頼",
}


# ---------------------------------------------------------------------------
# HTML レポートのデータモデル
# ---------------------------------------------------------------------------

@dataclass
class CheckRow:
    name: str
    finding: str
    score: int
    is_primary: bool   # True = js_dependency → 「最重要」タグ表示
    # 以下は web テンプレート用（静的テンプレートは使わない）
    score_color: str = ""
    bar_width: int = 0
    recommendations: list = field(default_factory=list)


@dataclass
class ActionRow:
    text: str
    type: str                    # "self" | "professional"
    cost: Optional[str] = None   # type=="professional" のときの費用目安


@dataclass
class ReportData:
    url: str           # 表示用URL(final_url)
    date: str          # "2026年6月12日"
    score: int
    status_label: str  # "良好" / "要改善" / "問題あり" / "重大"
    summary: str
    checks: list[CheckRow]    # is_primary 先・以降は score 昇順
    actions: list[ActionRow]  # priority 降順
    # 以下は P1/P3 用（デフォルト値付き・後方互換）
    count_critical: int = 0   # checks with score < 40
    count_warning: int = 0    # checks with score 40-69
    count_good: int = 0       # checks with score >= 70
    actions_high: list = field(default_factory=list)   # professional, check score < 40
    actions_mid: list = field(default_factory=list)    # professional 40-69 + all self
    actions_low: list = field(default_factory=list)    # llms_txt + 低優先度


# ---------------------------------------------------------------------------
# スコアヘルパー(render_markdown・json_writer から共用)
# ---------------------------------------------------------------------------

def _overall_score(results: list[CheckResult], weights: dict[str, float]) -> int:
    scored = [r for r in results if not r.skipped]
    if not scored:
        return 0
    total_w = sum(weights.get(r.check_id, 1.0) for r in scored)
    if total_w == 0:
        return 0
    s = sum(r.score * weights.get(r.check_id, 1.0) for r in scored)
    return round(s / total_w)


def _score_color_hex(score: int) -> str:
    """スコア帯に応じた16進カラーコード。全色定義はここに集約する。"""
    if score >= 70:
        return "#639922"
    if score >= 40:
        return "#BA7517"
    return "#E24B4A"


# ---------------------------------------------------------------------------
# HTML レポート用ヘルパー
# ---------------------------------------------------------------------------

def _status_label(score: int) -> str:
    if score >= 70:
        return "良好"
    if score >= 50:
        return "要改善"
    if score >= 40:
        return "問題あり"
    return "重大"


def _summary_text(score: int) -> str:
    if score >= 70:
        return "AIクローラーへの最適化が十分に整っています。"
    if score >= 50:
        return "いくつかの改善点があります。優先度の高いアクションから対応を始めてください。"
    if score >= 40:
        return "複数の課題が見つかりました。早めの対応をお勧めします。"
    return "AIクローラーに読み取られにくい状態です。早急な対応が必要です。"


def _primary_finding(r: CheckResult) -> str:
    """チェック結果から代表所見を1行で返す。最も深刻度が高い所見を採用。"""
    if r.skipped:
        return r.skip_reason or "検証不可"
    if not r.findings:
        return "問題は見つかりませんでした"
    return max(r.findings, key=lambda f: int(f.severity)).message


# ---------------------------------------------------------------------------
# ReportData 構築
# ---------------------------------------------------------------------------

def build_report_data(
    url: str,
    results: list[CheckResult],
    weights: dict[str, float],
    *,
    fetched_at: datetime | None = None,
) -> ReportData:
    """CheckResult リストから HTML レポート用データモデルを生成する。

    url には target.final_url を渡すこと。
    """
    fetched_at = fetched_at or datetime.now(timezone.utc)
    score = _overall_score(results, weights)

    rows = [
        CheckRow(
            name=r.title,
            finding=_primary_finding(r),
            score=r.score,
            is_primary=(r.check_id == "js_dependency"),
            score_color=_score_color_hex(r.score),
            bar_width=r.score,
            recommendations=[
                ActionRow(
                    text=rec.text,
                    type="self" if rec.effort == "self" else "professional",
                    cost=rec.cost_hint or None,
                )
                for rec in r.recommendations
            ],
        )
        for r in results
    ]
    # is_primary を先頭に、残りは score 昇順(問題が大きい順に上から並ぶ)
    rows.sort(key=lambda x: (not x.is_primary, x.score))

    all_recs = sorted(
        (rec for r in results for rec in r.recommendations),
        key=lambda rec: rec.priority,
        reverse=True,
    )
    actions = [
        ActionRow(
            text=rec.text,
            type="self" if rec.effort == "self" else "professional",
            cost=rec.cost_hint or None,
        )
        for rec in all_recs
    ]

    # count 系: results リストのスコアから
    count_critical = sum(1 for r in results if r.score < 40)
    count_warning  = sum(1 for r in results if 40 <= r.score < 70)
    count_good     = sum(1 for r in results if r.score >= 70)

    # アクション分類
    actions_high: list[ActionRow] = []
    actions_mid: list[ActionRow] = []
    actions_low: list[ActionRow] = []
    for r in results:
        for rec in r.recommendations:
            row = ActionRow(
                text=rec.text,
                type="self" if rec.effort == "self" else "professional",
                cost=rec.cost_hint or None,
            )
            if r.check_id == "llms_txt":
                actions_low.append(row)
            elif rec.effort == "self":
                actions_mid.append(row)   # 自社対応は全てミドル
            elif r.score < 40:
                actions_high.append(row)  # プロ依頼 × 重大 → 高
            else:
                actions_mid.append(row)   # プロ依頼 × 40+ → ミドル

    d = fetched_at.astimezone(timezone.utc)
    return ReportData(
        url=url,
        date=f"{d.year}年{d.month}月{d.day}日",
        score=score,
        status_label=_status_label(score),
        summary=_summary_text(score),
        checks=rows,
        actions=actions,
        count_critical=count_critical,
        count_warning=count_warning,
        count_good=count_good,
        actions_high=actions_high,
        actions_mid=actions_mid,
        actions_low=actions_low,
    )


# ---------------------------------------------------------------------------
# HTML レンダリング
# ---------------------------------------------------------------------------

def render_html(data: ReportData) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["score_color"] = _score_color_hex
    # スコア帯に応じた背景色・文字色フィルター（P1/P3バッジ用）
    env.filters["score_bg"]   = lambda s: "#FCEBEB" if s < 40 else ("#FAEEDA" if s < 70 else "#EAF3DE")
    env.filters["score_text"] = lambda s: "#A32D2D" if s < 40 else ("#854F0B" if s < 70 else "#3B6D11")

    # 旧テンプレート互換で残す（テスト参照）
    dashoffset = round(314 * (1 - data.score / 100), 1)

    return env.get_template("report.html.j2").render(
        url=data.url,
        date=data.date,
        score=data.score,
        score_color=_score_color_hex(data.score),
        dashoffset=dashoffset,
        status_label=data.status_label,
        summary=data.summary,
        checks=data.checks,
        actions=data.actions,
        count_critical=data.count_critical,
        count_warning=data.count_warning,
        count_good=data.count_good,
        actions_high=data.actions_high,
        actions_mid=data.actions_mid,
        actions_low=data.actions_low,
    )


# ---------------------------------------------------------------------------
# Web HTML レンダリング（インタラクティブ）
# ---------------------------------------------------------------------------

def render_web_html(data: ReportData) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["score_color"] = _score_color_hex
    donut_offset = round(251 * (1 - data.score / 100), 1)
    return env.get_template("report_web.html.j2").render(
        url=data.url,
        date=data.date,
        score=data.score,
        score_color=_score_color_hex(data.score),
        donut_offset=donut_offset,
        status_label=data.status_label,
        summary=data.summary,
        checks=data.checks,
        actions=data.actions,
    )


# ---------------------------------------------------------------------------
# PDF レンダリング
# ---------------------------------------------------------------------------

def render_pdf(html: str) -> bytes:
    """HTML 文字列を PDF バイト列に変換する。

    WeasyPrint が利用できない環境では ImportError を送出する。
    Windows では GTK/Cairo ランタイムが必要。インストール手順:
      https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows
    """
    try:
        from weasyprint import HTML as _HTML  # noqa: PLC0415
    except (ImportError, OSError) as exc:
        raise ImportError(
            "WeasyPrint が利用できません。PDF 出力を使うには以下を確認してください:\n"
            "  1. uv add weasyprint\n"
            "  2. Windows の場合は GTK3 ランタイムが別途必要です:\n"
            "     https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows"
        ) from exc
    return _HTML(string=html).write_pdf()


# ---------------------------------------------------------------------------
# Markdown レンダリング(後方互換)
# ---------------------------------------------------------------------------

def _overall_label(score: int) -> str:
    if score >= 80:
        return "良好"
    if score >= 50:
        return "要改善"
    return "重大"


def _top_improvements(results: list[CheckResult], limit: int = 3):
    recs = [rec for r in results for rec in r.recommendations]
    recs.sort(key=lambda r: r.priority, reverse=True)
    return recs[:limit]


def _build_context(url, results, weights, fetched_at):
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


def render_markdown(
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
    ctx = _build_context(url, results, weights, fetched_at or datetime.now(timezone.utc))
    return env.get_template("report.md.j2").render(**ctx)


# 後方互換エイリアス(test_report.py / json_writer.py が参照)
render_report = render_markdown
