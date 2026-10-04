"""比較軸(criteria)の固定候補と、criterion文字列の共通検証ロジック。

Phase 2ではAI自動提案を行わず、この固定リストからユーザーが選ぶ方式にしていた。
Phase 5Aから、この固定候補は「おすすめ」として残しつつ、ユーザーが自由入力した
任意の文字列も比較軸として受け付けられるようにしている
(app/schemas/research.py::ResearchCreate.criteria、README参照)。
Frontend側にも同じ候補の日本語ラベルを表示用として持たせている
(バックエンドはAPIとして提供していないため、重複はあるが許容している)。

Phase 5Cから、criterion文字列1件分の検証(trim・長さ・制御文字)を
`validate_criterion_text()`としてここに集約している。
`app/schemas/research.py`(POST /research)と
`app/services/suggestion_service.py`(POST /suggest-criteria、AI提案の
defense-in-depth検証)の両方がこれを再利用し、同じルールを別実装しない。
"""

import re
from enum import Enum


class Criterion(str, Enum):
    learning_curve = "learning_curve"
    development_speed = "development_speed"
    ai_compatibility = "ai_compatibility"
    performance = "performance"
    async_support = "async_support"
    type_safety = "type_safety"
    deployability = "deployability"
    ecosystem = "ecosystem"
    operability = "operability"
    cost = "cost"


# criterion文字列に許可しない制御文字(改行・タブ・DEL等)。自由入力の
# criterionがGeminiへのprompt構造に意図せず混入するのを防ぐ簡易的な対策。
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
MAX_CRITERION_LENGTH = 40


CRITERION_LABELS: dict[Criterion, str] = {
    Criterion.learning_curve: "学びやすさ",
    Criterion.development_speed: "開発速度",
    Criterion.ai_compatibility: "AIアプリとの相性",
    Criterion.performance: "処理性能",
    Criterion.async_support: "非同期処理",
    Criterion.type_safety: "型安全性",
    Criterion.deployability: "デプロイしやすさ",
    Criterion.ecosystem: "エコシステム",
    Criterion.operability: "運用しやすさ",
    Criterion.cost: "コスト",
}


def label_for(criterion: str) -> str:
    """criterionの表示ラベルを返す。

    固定候補(Criterion)であればCRITERION_LABELSの日本語ラベルを、
    それ以外(ユーザーの自由入力)は入力された文字列自体をラベルとして扱う。
    MVPでは自由入力のcriterionに対してslug生成等は行わず、内部キー
    (criterion)と表示ラベル(criterion_label)を同じ文字列にする。
    """
    try:
        return CRITERION_LABELS[Criterion(criterion)]
    except ValueError:
        return criterion


# Phase 5D-c: Query Language Strategy。固定criteriaについてのみ、Tavily検索
# クエリ(item_a/item_b向け、英語中心のofficial/primary retrieval用)に使う
# 英語search termを用意する。CRITERION_LABELS(日本語)と対になる表だが、
# 用途は異なる(表示用ではなく検索クエリ用)。
#
# 各criterionにつき1語/1フレーズの、意味的に忠実な直訳のみとする
# ("tutorial" "plugins"のような関連語への拡張はしない)。これはquery
# languageそのものの効果(日本語→英語)と、criteria keywordの拡張効果を
# 混同しないため(Phase 5D-c設計時の明示的な方針)。
CRITERION_ENGLISH_SEARCH_TERMS: dict[Criterion, str] = {
    Criterion.learning_curve: "learning curve",
    Criterion.development_speed: "development speed",
    Criterion.ai_compatibility: "AI compatibility",
    Criterion.performance: "performance",
    Criterion.async_support: "async support",
    Criterion.type_safety: "type safety",
    Criterion.deployability: "deployability",
    Criterion.ecosystem: "ecosystem",
    Criterion.operability: "operability",
    Criterion.cost: "cost",
}


def english_search_term_for(criterion: str) -> str | None:
    """criterionの英語search termを返す(Phase 5D-c、検索クエリ専用)。

    固定候補(Criterion)であればCRITERION_ENGLISH_SEARCH_TERMSの値を返す。
    それ以外(ユーザーの自由入力、多くは日本語を含みうる)は、正確な英訳を
    機械的に保証できないため`None`を返す(呼び出し側はNoneを「英語クエリ
    には含めない」の意味で扱う。label_for()のように入力文字列をそのまま
    返すフォールバックはしない点がlabel_for()と異なる)。
    """
    try:
        return CRITERION_ENGLISH_SEARCH_TERMS[Criterion(criterion)]
    except ValueError:
        return None


def canonical_key_for(criterion: str) -> str:
    """重複判定用の正規化キーを返す。

    固定候補のkey(例: "cost")とlabel(例: "コスト")は、意味的には同じ
    criterionを指すため、同じ正規化キーへ変換して重複として扱う。
    それ以外(自由入力同士)は、大文字小文字を無視した値そのものを返す。

    既存の固定key↔label対応表だけを対象にした単純な正規化であり、
    類義語判定やLLMによる意味判定は行わない。
    """
    trimmed = criterion.strip()
    lowered = trimmed.lower()

    try:
        return Criterion(lowered).value
    except ValueError:
        pass

    for candidate, label in CRITERION_LABELS.items():
        if label == trimmed:
            return candidate.value

    return lowered


def validate_criterion_text(raw: str) -> str:
    """criterion文字列1件分を検証し、trim済みの文字列を返す。

    空文字・上限文字数超過・制御文字のいずれかに該当する場合はValueErrorを
    送出する(重複判定はcanonical_key_for()を使って呼び出し側で行う。
    このtrimmed値はどのcriterionにも同じ意味を持つため、ここでは扱わない)。
    """
    trimmed = raw.strip()

    if not trimmed:
        raise ValueError("比較軸を空文字にすることはできません。")
    if len(trimmed) > MAX_CRITERION_LENGTH:
        raise ValueError(
            f"比較軸は{MAX_CRITERION_LENGTH}文字以内で入力してください: {trimmed[:20]}..."
        )
    if CONTROL_CHAR_PATTERN.search(trimmed):
        raise ValueError("比較軸に改行や制御文字を含めることはできません。")

    return trimmed
