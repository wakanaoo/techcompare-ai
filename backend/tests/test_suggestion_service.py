"""suggestion_service.filter_and_cap_suggestions() のテスト。

Suggest Pointsのbackend側defense-in-depth検証(要件6): trim・空文字禁止・
長さ制約・制御文字禁止・existing_criteriaとのduplicate除外・提案同士の
duplicate除外・最大5件capを、既存app/schemas/criteria.pyのロジックを
再利用して確認する。
"""

from app.services.llm_schemas import CriterionSuggestionItem
from app.services.suggestion_service import MAX_SUGGESTIONS, filter_and_cap_suggestions


def _item(name: str, reason: str = "理由") -> CriterionSuggestionItem:
    return CriterionSuggestionItem(name=name, reason=reason)


def test_accepts_valid_unique_suggestions():
    suggestions = [_item("スキーマ柔軟性"), _item("クエリ能力")]

    result = filter_and_cap_suggestions(suggestions, existing_criteria=[])

    assert [s.name for s in result] == ["スキーマ柔軟性", "クエリ能力"]


def test_trims_whitespace_in_name_and_reason():
    suggestions = [_item("  スキーマ柔軟性  ", "  理由  ")]

    result = filter_and_cap_suggestions(suggestions, existing_criteria=[])

    assert result[0].name == "スキーマ柔軟性"
    assert result[0].reason == "理由"


def test_rejects_empty_name():
    suggestions = [_item("   "), _item("有効な提案")]

    result = filter_and_cap_suggestions(suggestions, existing_criteria=[])

    assert [s.name for s in result] == ["有効な提案"]


def test_rejects_name_exceeding_max_length():
    suggestions = [_item("a" * 41), _item("a" * 40)]

    result = filter_and_cap_suggestions(suggestions, existing_criteria=[])

    assert len(result) == 1
    assert result[0].name == "a" * 40


def test_rejects_name_with_control_characters():
    suggestions = [_item("開発速度\n改行混入"), _item("正常な提案")]

    result = filter_and_cap_suggestions(suggestions, existing_criteria=[])

    assert [s.name for s in result] == ["正常な提案"]


def test_dedupes_suggestions_against_each_other_by_canonical_key():
    """固定候補のkey/labelの往復を含め、提案同士の重複はcanonical_key_for()
    で判定される(既存criteria.pyのロジックをそのまま再利用)。"""
    suggestions = [_item("cost"), _item("コスト"), _item("Cost")]

    result = filter_and_cap_suggestions(suggestions, existing_criteria=[])

    assert len(result) == 1
    assert result[0].name == "cost"


def test_dedupes_suggestions_against_existing_criteria():
    suggestions = [_item("開発速度"), _item("運用しやすさ")]

    result = filter_and_cap_suggestions(
        suggestions, existing_criteria=["development_speed"]
    )

    # "開発速度"(development_speedのlabel)はexisting_criteriaの
    # "development_speed"と同じcanonical keyなので除外される。
    assert [s.name for s in result] == ["運用しやすさ"]


def test_caps_at_max_suggestions():
    suggestions = [_item(f"提案{i}") for i in range(MAX_SUGGESTIONS + 3)]

    result = filter_and_cap_suggestions(suggestions, existing_criteria=[])

    assert len(result) == MAX_SUGGESTIONS


def test_empty_suggestions_returns_empty_list():
    assert filter_and_cap_suggestions([], existing_criteria=[]) == []
