"""診断チェックのレジストリ。

各モジュールは CHECK_ID / TITLE / WEIGHT / run(target)->CheckResult を公開する。
v1スコープ: bot_access, llms_txt, js_dependency, structured_data, semantic_html, freshness の6項目。
"""

from . import bot_access, freshness, js_dependency, llms_txt, semantic_html, structured_data

# 実行順 = レポート掲載順(CLAUDE.mdのv1スコープ番号順)。
CHECKS = [bot_access, llms_txt, js_dependency, structured_data, semantic_html, freshness]

__all__ = [
    "CHECKS",
    "bot_access",
    "llms_txt",
    "js_dependency",
    "structured_data",
    "semantic_html",
    "freshness",
]
