"""bot_access の単体テスト。HEADプローブは monkeypatch でネットワークを排除。"""

from __future__ import annotations

from ai_audit.checks import bot_access
from tests.conftest import make_target, read_fixture


def _no_server_block(*args, **kwargs):
    """全ボット200(サーバ側ブロックなし)を返すHEADプローブの差し替え。"""
    return {b: 200 for b in bot_access.AI_BOTS}


# --- robots解析(純粋関数) ----------------------------------------------------


def test_analyze_robots_allow_all():
    # 正常系: 全ボット許可
    blocked = bot_access.analyze_robots(read_fixture("robots_allow_all.txt"))
    assert not any(blocked.values())


def test_analyze_robots_blocks_only_gptbot():
    # 問題検出系: GPTBotだけブロック
    blocked = bot_access.analyze_robots(read_fixture("robots_block_gptbot.txt"))
    assert blocked["GPTBot"] is True
    assert blocked["ClaudeBot"] is False


def test_analyze_robots_block_all():
    blocked = bot_access.analyze_robots(read_fixture("robots_block_all.txt"))
    assert all(blocked.values())


def test_analyze_robots_missing_is_not_blocked():
    # robots.txt不在 → ブロックなし扱い
    assert not any(bot_access.analyze_robots(None).values())


def test_analyze_robots_garbled_input():
    # 壊れた入力: 文字化け/不正行でも例外を出さず、安全側(ブロックなし)に倒す
    garbled = "\x00\xff???? not a robots file \n User-agent \n :::"
    blocked = bot_access.analyze_robots(garbled)
    assert isinstance(blocked, dict)
    assert not any(blocked.values())


# --- run() 統合(HEADはmonkeypatch) ------------------------------------------


def test_run_full_access(monkeypatch):
    monkeypatch.setattr(bot_access, "probe_bot_blocks", _no_server_block)
    t = make_target(robots_txt=read_fixture("robots_allow_all.txt"))
    result = bot_access.run(t)
    assert result.score == 100
    assert result.check_id == "bot_access"


def test_run_detects_robots_block(monkeypatch):
    monkeypatch.setattr(bot_access, "probe_bot_blocks", _no_server_block)
    t = make_target(robots_txt=read_fixture("robots_block_gptbot.txt"))
    result = bot_access.run(t)
    # 8ボット中1つブロック → 7/8 = 88
    assert result.score == round(7 / 8 * 100)
    assert any("GPTBot" in f.message for f in result.findings)
    assert any(r.effort == "self" for r in result.recommendations)


def test_run_detects_server_block(monkeypatch):
    # サーバ側で全ボット403 → robotsは許可でもスコア0
    monkeypatch.setattr(
        bot_access,
        "probe_bot_blocks",
        lambda *a, **k: {b: 403 for b in bot_access.AI_BOTS},
    )
    t = make_target(robots_txt=read_fixture("robots_allow_all.txt"))
    result = bot_access.run(t)
    assert result.score == 0
    assert any(r.effort == "vendor" for r in result.recommendations)


def test_run_survives_probe_failure(monkeypatch):
    # HEADプローブが例外でも graceful degradation(robots結果だけで継続)
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(bot_access, "probe_bot_blocks", boom)
    t = make_target(robots_txt=read_fixture("robots_allow_all.txt"))
    result = bot_access.run(t)
    assert result.score == 100
