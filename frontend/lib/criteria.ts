/**
 * 比較軸の固定候補。
 *
 * Backend(app/schemas/criteria.py)と同じkey/labelの組を持たせている。
 * Phase 2ではAI自動提案を行わず、この固定リストから選ぶ方式にしているため、
 * Frontend側にも同じ候補を静的データとして持たせている(重複はあるが許容)。
 */

export interface CriterionOption {
  key: string;
  label: string;
}

export const CRITERION_OPTIONS: CriterionOption[] = [
  { key: "learning_curve", label: "学びやすさ" },
  { key: "development_speed", label: "開発速度" },
  { key: "ai_compatibility", label: "AIアプリとの相性" },
  { key: "performance", label: "処理性能" },
  { key: "async_support", label: "非同期処理" },
  { key: "type_safety", label: "型安全性" },
  { key: "deployability", label: "デプロイしやすさ" },
  { key: "ecosystem", label: "エコシステム" },
  { key: "operability", label: "運用しやすさ" },
  { key: "cost", label: "コスト" },
];

export const MIN_CRITERIA = 1;
export const MAX_CRITERIA = 5;

// New Research画面を開いた時点でのデフォルト選択(ユーザーが何も触らなくても
// 最低1つは選ばれている状態にするため)。
export const DEFAULT_CRITERIA = [
  "development_speed",
  "ai_compatibility",
  "learning_curve",
];
