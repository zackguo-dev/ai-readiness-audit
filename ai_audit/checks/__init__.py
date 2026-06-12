"""診断チェックのレジストリ。

各モジュールは CHECK_ID / TITLE / WEIGHT / run(target)->CheckResult を公開する。
v1スコープ: bot_access, llms_txt の2項目(js_dependency以降は次セッション)。
"""

from . import bot_access, llms_txt

# 実行順 = レポート掲載順。
CHECKS = [bot_access, llms_txt]

__all__ = ["CHECKS", "bot_access", "llms_txt"]
