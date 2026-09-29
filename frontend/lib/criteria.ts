/**
 * 比較軸の「おすすめ」候補。
 *
 * Phase 5C Finishingから、Direct Compare(Home)の固定候補もExplore経由の
 * Compare Setup(Base Points、`lib/catalog.ts::getBaseComparisonCriteria()`)と
 * 同じ「英語の自然文ラベル = 実際にPOST /researchへ送る値」という形に統一した。
 *
 * backend(app/schemas/criteria.py::label_for())は、既知のCriterion enumと
 * 一致しない文字列をそのまま表示ラベルとして扱うため、この変更にbackend側の
 * 対応は不要(Compare SetupのBase Pointsが既にこの経路で英語のまま
 * Comparison Reportに表示されている。README/E2E確認済み)。
 * 以前の日本語ラベル+snake_case keyの対応表はbackend側にのみ残っているが、
 * どちらの画面からも新しいResearchでは使われなくなる(過去に作成済みの
 * Researchの表示には影響しない)。
 *
 * 意味が分かりにくい英語ラベルのために、各候補へ短い日本語説明
 * (`description`)を持たせている。表示は`InfoTooltip`(hover/focus/tap)で行う。
 */

export interface CriterionOption {
  label: string;
  description: string;
}

export const CRITERION_OPTIONS: CriterionOption[] = [
  {
    label: "Learning curve",
    description: "習得のしやすさ。ドキュメントの分かりやすさや、必要な前提知識の少なさ。",
  },
  {
    label: "Development speed",
    description: "機能をどれだけ早く実装・検証できるか。",
  },
  {
    label: "AI app fit",
    description: "LLMや生成AIを組み込んだアプリを作るうえでの相性の良さ。",
  },
  {
    label: "Performance",
    description: "処理速度やスループットなど、実行時の性能。",
  },
  {
    label: "Async support",
    description: "非同期処理(async/await等)をどれだけ自然に扱えるか。",
  },
  {
    label: "Type safety",
    description: "型によって、実行前に誤りを検出しやすいか。",
  },
  {
    label: "Deployability",
    description: "本番環境へのデプロイのしやすさ。",
  },
  {
    label: "Ecosystem",
    description: "ライブラリ・情報・コミュニティの充実度。",
  },
  {
    label: "Operability",
    description: "運用・監視・保守のしやすさ。",
  },
  {
    label: "Cost",
    description: "利用・運用にかかる費用。",
  },
];

export const MIN_CRITERIA = 1;
export const MAX_CRITERIA = 5;

// backend(app/schemas/research.py)のバリデーションと同じ上限。
// ここでの制限は体験を早く返すためのものであり、最終的な検証は
// backend側で行われる。
export const MAX_CRITERION_LENGTH = 40;

// New Research画面を開いた時点でのデフォルト選択(ユーザーが何も触らなくても
// 最低1つは選ばれている状態にするため)。
export const DEFAULT_CRITERIA = ["Development speed", "AI app fit", "Learning curve"];

/**
 * 重複判定用の正規化キーを返す(backend app/schemas/criteria.py::
 * canonical_key_for()と同じ「意味」を持たせているが、こちらは固定候補が
 * すべて英語ラベルそのものになったため、大文字小文字を無視した比較のみで
 * 十分)。固定候補と一致すればその正規形(小文字化したlabel)を、それ以外
 * (自由入力・AI提案)は入力値そのものを小文字化した文字列を返す。
 * 類義語判定やLLMによる意味判定はしない。
 */
export function canonicalCriterionKey(value: string): string {
  const trimmed = value.trim();
  const lowered = trimmed.toLowerCase();

  const match = CRITERION_OPTIONS.find((option) => option.label.toLowerCase() === lowered);
  return match ? match.label.toLowerCase() : lowered;
}

/** ラベル文字列から、対応するCriterionOption(説明つき)を探す(tooltip表示用)。 */
export function getCriterionOption(value: string): CriterionOption | undefined {
  const canonical = canonicalCriterionKey(value);
  return CRITERION_OPTIONS.find((option) => option.label.toLowerCase() === canonical);
}
