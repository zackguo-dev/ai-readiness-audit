"""llms_txt の単体テスト(ネットワーク非依存)。"""

from __future__ import annotations

from ai_audit.checks import llms_txt
from tests.conftest import make_target, read_fixture


def test_valid_llms_txt_scores_full():
    # 正常系: 有効な形式 → 100
    t = make_target(llms_txt=read_fixture("llms_valid.txt"))
    result = llms_txt.run(t)
    assert result.score == 100


def test_valid_with_full_variant():
    t = make_target(
        llms_txt=read_fixture("llms_valid.txt"),
        llms_full_txt=read_fixture("llms_valid.txt"),
    )
    result = llms_txt.run(t)
    assert result.score == 100
    assert any("llms-full.txt" in f.message for f in result.findings)


def test_invalid_llms_txt_scores_partial():
    # 問題検出系: 形式不備 → 60、改善提案あり
    t = make_target(llms_txt=read_fixture("llms_invalid.txt"))
    result = llms_txt.run(t)
    assert result.score == 60
    assert result.recommendations


def test_absent_llms_txt_is_lenient():
    # 不在は重大欠陥扱いしない(誠実性ルール) → 50、INFOのみ
    t = make_target(llms_txt=None)
    result = llms_txt.run(t)
    assert result.score == 50
    assert all(f.severity.name == "INFO" for f in result.findings)


def test_garbled_llms_txt_does_not_crash():
    # 壊れた入力: 制御文字混じりでも例外を出さない
    t = make_target(llms_txt="\x00\x01 ### \n ][(( garbled")
    result = llms_txt.run(t)
    assert 0 <= result.score <= 100
