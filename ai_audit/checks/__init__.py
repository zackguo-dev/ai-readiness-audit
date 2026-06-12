"""診断チェックのレジストリ。

各モジュールは CHECK_ID / TITLE / WEIGHT / run(target)->CheckResult を公開する。
v1スコープ: bot_access, llms_txt, js_dependency, structured_data, semantic_html の5項目
(freshness は次セッション)。
"""

from . import bot_access, js_dependency, llms_txt, semantic_html, structured_data

# 実行順 = レポート掲載順(CLAUDE.mdのv1スコープ番号順)。
CHECKS = [bot_access, llms_txt, js_dependency, structured_data, semantic_html]

__all__ = [
    "CHECKS",
    "bot_access",
    "llms_txt",
    "js_dependency",
    "structured_data",
    "semantic_html",
]
