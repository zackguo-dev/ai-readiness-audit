"""機械可読JSON診断結果の保存。

results/{domain}/{ISO8601タイムスタンプ}.json に毎回自動保存する。
スキーマはCheckResultの最小シリアライズ。履歴比較・グラフ化はv1スコープ外。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ..checks.base import CheckResult
from .renderer import _overall_score


def save_results_json(
    url: str,
    final_url: str,
    fetched_at: datetime,
    results: list[CheckResult],
    weights: dict[str, float],
    base_dir: Path = Path("results"),
) -> Path:
    """診断結果をJSONファイルに保存し、保存先パスを返す。"""
    domain = urlparse(final_url or url).netloc or "unknown"
    # Windows安全なISO 8601基本形式(コロン・プラス記号を含まない)
    timestamp = fetched_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    out_dir = base_dir / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{timestamp}.json"

    payload = {
        "url": url,
        "final_url": final_url,
        "fetched_at": fetched_at.isoformat(),
        "overall_score": _overall_score(results, weights),
        "checks": [_serialize_result(r) for r in results],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _serialize_result(r: CheckResult) -> dict:
    return {
        "check_id": r.check_id,
        "title": r.title,
        "score": r.score,
        "skipped": r.skipped,
        "skip_reason": r.skip_reason,
        "findings": [
            {"severity": int(f.severity), "message": f.message, "detail": f.detail}
            for f in r.findings
        ],
        "recommendations": [
            {
                "text": rec.text,
                "effort": rec.effort,
                "cost_hint": rec.cost_hint,
                "priority": rec.priority,
            }
            for rec in r.recommendations
        ],
    }
