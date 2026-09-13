/**
 * 比較軸の「おすすめ」候補。
 *
 * Backend(app/schemas/criteria.py)と同じkey/labelの組を持たせている。
 * Phase 5Aから、この固定候補は「おすすめ」チップとして残しつつ、
 * ユーザーは自由入力で任意の比較軸も追加できる
 * (backend側もCriterion enum固定ではなく任意文字列を受け付ける、
 * app/schemas/research.py::ResearchCreate.criteria参照)。
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

// backend(app/schemas/research.py)のバリデーションと同じ上限。
// ここでの制限は体験を早く返すためのものであり、最終的な検証は
// backend側で行われる。
export const MAX_CRITERION_LENGTH = 40;

// New Research画面を開いた時点でのデフォルト選択(ユーザーが何も触らなくても
// 最低1つは選ばれている状態にするため)。
export const DEFAULT_CRITERIA = [
  "development_speed",
  "ai_compatibility",
  "learning_curve",
];

/**
 * 重複判定用の正規化キーを返す(backend app/schemas/criteria.py::
 * canonical_key_for()と同じロジック)。
 *
 * 固定候補のkey(例: "cost")とlabel(例: "コスト")は表記が異なるが
 * 意味的には同じ項目なので、同じ正規化キーへ変換して重複として扱う。
 * それ以外(自由入力同士)は大文字小文字を無視した値そのもの。
 * 類義語判定やLLMによる意味判定はしない。
 */
export function canonicalCriterionKey(value: string): string {
  const trimmed = value.trim();
  const lowered = trimmed.toLowerCase();

  const byKey = CRITERION_OPTIONS.find((option) => option.key.toLowerCase() === lowered);
  if (byKey) return byKey.key;

  const byLabel = CRITERION_OPTIONS.find((option) => option.label === trimmed);
  if (byLabel) return byLabel.key;

  return lowered;
}
