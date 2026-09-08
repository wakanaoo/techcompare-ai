"""比較軸(criteria)の固定候補。

Phase 2ではAI自動提案を行わず、この固定リストからユーザーが選ぶ方式にする。
Frontend側にも同じ候補の日本語ラベルを表示用として持たせている
(バックエンドはAPIとして提供していないため、重複はあるが許容している)。
"""

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
