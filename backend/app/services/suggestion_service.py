"""Suggest Points(POST /suggest-criteria)のLLM応答を検証・整形する処理。

Geminiの提案は既にPydantic(CriteriaSuggestionsResult)でパースされているが、
それだけでは「existing_criteriaと重複している」「制御文字を含む」
「6件以上返ってきた」といった、Structured Outputのスキーマだけでは防げない
ケースを防げない。ここでbackend側のdefense-in-depth検証を行う
(frontend側でも既存のcanonicalCriterionKey()によるduplicate防止は別途行う。
このモジュールはそれを信頼せず、backend単独でも安全であることを保証する)。

既存のapp/schemas/criteria.pyのvalidate_criterion_text() /
canonical_key_for()をそのまま再利用し、同じルールを別実装しない。
"""

from app.schemas.criteria import canonical_key_for, validate_criterion_text
from app.services.llm_schemas import CriterionSuggestionItem

# 既存ResearchCreate.criteria(app/schemas/research.py)のmax_length=5と
# 揃える。Suggest Pointsの提案もこの5件を超えて返さない。
MAX_SUGGESTIONS = 5


def filter_and_cap_suggestions(
    suggestions: list[CriterionSuggestionItem],
    existing_criteria: list[str],
) -> list[CriterionSuggestionItem]:
    """Geminiの提案リストを検証・重複除去し、最大MAX_SUGGESTIONS件に絞る。

    以下を順に適用する:
      - name のtrim・空文字禁止・長さ制約・制御文字禁止
        (validate_criterion_text()、既存criteria検証と同じルール)
      - existing_criteria とのcanonical key重複除外
      - 提案同士のcanonical key重複除外
      - 最大MAX_SUGGESTIONS件へのcap

    不正な提案(検証に失敗したもの)はエラーにせず、黒く読み飛ばす
    (Suggest Pointsは補助機能であり、1件不正でも全体を失敗させる必要は
    ないため)。意味的な類義語判定(例: 「速度」と「パフォーマンス」)は
    行わない。
    """
    seen_keys: set[str] = {
        canonical_key_for(c) for c in existing_criteria if c.strip()
    }
    accepted: list[CriterionSuggestionItem] = []

    for item in suggestions:
        try:
            name = validate_criterion_text(item.name)
        except ValueError:
            continue

        key = canonical_key_for(name)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        reason = item.reason.strip()
        accepted.append(CriterionSuggestionItem(name=name, reason=reason))

        if len(accepted) >= MAX_SUGGESTIONS:
            break

    return accepted
