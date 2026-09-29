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
