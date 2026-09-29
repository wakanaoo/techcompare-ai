"use client";

import { useState } from "react";

import { MAX_CRITERIA, MAX_CRITERION_LENGTH, canonicalCriterionKey } from "@/lib/criteria";

/**
 * 比較ポイント(criteria)の選択状態を管理する共通フック。
 *
 * 元々app/page.tsx(Home、Direct Compare)にベタ書きされていたロジックを
 * Phase 5Cで抽出した。挙動は完全に維持している(canonicalCriterionKey()
 * による重複判定、MAX_CRITERIAでの上限、custom入力のtrim/長さ/重複検証)。
 *
 * `toggleCriterion()`は「固定候補チップ」「追加済みcustomチップの削除」の
 * どちらにも使われていたのと同じ理由で、Compare Setup側のBase Points
 * チップ・AI Suggestionsチップにもそのまま再利用できる(chipの追加/削除は
 * 出自(base/AI/custom/fixed)を問わず同じ「正規化キーで見つけて
 * トグルする」処理で表現できるため)。
 */
export interface UseCriteriaSelectionResult {
  criteria: string[];
  customInput: string;
  setCustomInput: (value: string) => void;
  criteriaError: string | null;
  /** 正規化キーで既存の選択と照合し、あれば削除・無ければ追加する(上限あり)。 */
  toggleCriterion: (value: string) => void;
  /** customInputの内容を検証のうえ選択に追加し、成功したらcustomInputを空にする。 */
  addCustomCriterion: () => void;
  reachedMaxCriteria: boolean;
}

export function useCriteriaSelection(
  initialCriteria: string[] = [],
): UseCriteriaSelectionResult {
  const [criteria, setCriteria] = useState<string[]>(initialCriteria);
  const [customInput, setCustomInput] = useState("");
  const [criteriaError, setCriteriaError] = useState<string | null>(null);

  function toggleCriterion(value: string) {
    const canonicalTarget = canonicalCriterionKey(value);

    setCriteria((current) => {
      const existingMatch = current.find(
        (c) => canonicalCriterionKey(c) === canonicalTarget,
      );
      if (existingMatch !== undefined) {
        return current.filter((c) => c !== existingMatch);
      }
      if (current.length >= MAX_CRITERIA) {
        return current;
      }
      return [...current, value];
    });
  }

  function addCustomCriterion() {
    const trimmed = customInput.trim();
    setCriteriaError(null);

    if (!trimmed) return;

    if (trimmed.length > MAX_CRITERION_LENGTH) {
      setCriteriaError(`項目は${MAX_CRITERION_LENGTH}文字以内で入力してください`);
      return;
    }
    if (criteria.length >= MAX_CRITERIA) {
      setCriteriaError(`項目は最大${MAX_CRITERIA}個までです`);
      return;
    }
    // 固定候補のkey↔labelも含めて正規化して重複を判定する
    // (backendのcanonical_key_for()と同じロジック)。
    const dedupeKey = canonicalCriterionKey(trimmed);
    if (criteria.some((c) => canonicalCriterionKey(c) === dedupeKey)) {
      setCriteriaError("その項目はすでに追加されています");
      return;
    }

    setCriteria((current) => [...current, trimmed]);
    setCustomInput("");
  }

  return {
    criteria,
    customInput,
    setCustomInput,
    criteriaError,
    toggleCriterion,
    addCustomCriterion,
    reachedMaxCriteria: criteria.length >= MAX_CRITERIA,
  };
}
