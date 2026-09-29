"use client";

import { useState } from "react";

import type { UseCriteriaSelectionResult } from "@/hooks/useCriteriaSelection";
import { suggestCriteria, type CriterionSuggestion } from "@/lib/api";
import { canonicalCriterionKey } from "@/lib/criteria";
import { Button } from "./Button";

interface SuggestPointsPanelProps {
  itemA: string;
  itemB: string;
  goal: string;
  /** existing_criteria として送るBase Points(その時点で表示されている候補一覧)。 */
  basePoints: string[];
  criteria: UseCriteriaSelectionResult;
}

type Status = "idle" | "loading" | "success" | "error";

/**
 * Suggest Points(Phase 5C Finishing 追補v4)。
 *
 * 明示的なbutton actionでのみGeminiを1回呼ぶ(入力のたびの自動呼び出しは
 * 禁止)。Tavilyは呼ばない・Research/Source/Evidenceも作らない
 * (POST /suggest-criteriaの責務、このコンポーネントはUIのみ)。
 * エラー時もボタンは押せる状態のままにし、ユーザー自身が再試行できる。
 *
 * UIに表示するエラー文言は、status codeやprovider名などの技術的詳細を
 * 含まない固定の一般向けメッセージにする(技術的詳細は`console.error`にのみ
 * 残す)。`lib/api.ts::suggestCriteria()`が投げるErrorのmessageそのもの
 * (backendのdetailを含む)はUIには出さない。
 */
export function SuggestPointsPanel({
  itemA,
  itemB,
  goal,
  basePoints,
  criteria,
}: SuggestPointsPanelProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [suggestions, setSuggestions] = useState<CriterionSuggestion[]>([]);
  const [error, setError] = useState<string | null>(null);

  const trimmedGoal = goal.trim();
  const canSuggest = trimmedGoal.length > 0 && status !== "loading";

  async function handleSuggest() {
    if (!canSuggest) return;

    setStatus("loading");
    setError(null);

    try {
      const result = await suggestCriteria({
        item_a: itemA,
        item_b: itemB,
        goal: trimmedGoal,
        existing_criteria: basePoints,
      });
      setSuggestions(result.suggestions);
      setStatus("success");
    } catch (err) {
      // 技術的な詳細(status code・provider名等)はconsoleにのみ残し、
      // UIには一般向けの固定メッセージだけを出す。
      console.error("Suggest Points request failed:", err);
      setError("提案を取得できませんでした。もう一度お試しください。");
      setStatus("error");
    }
  }

  return (
    <div className="suggest-points">
      <div className="suggest-points__header">
        <Button
          type="button"
          variant="secondary"
          onClick={handleSuggest}
          disabled={!canSuggest}
          loading={status === "loading"}
          title={!trimmedGoal ? "Use Caseを入力すると提案できます" : undefined}
        >
          {status === "error" ? "Retry Suggest Points" : "Suggest Points"}
        </Button>
      </div>

      {status === "error" && error && (
        <p className="suggest-points__error" role="alert">
          {error}
        </p>
      )}

      {status === "success" && suggestions.length === 0 && (
        <p className="suggest-points__hint">追加の提案はありませんでした。</p>
      )}

      {suggestions.length > 0 && (
        <ul className="ai-suggestion-list">
          {suggestions.map((suggestion) => {
            const canonicalTarget = canonicalCriterionKey(suggestion.name);
            const selected = criteria.criteria.some(
              (c) => canonicalCriterionKey(c) === canonicalTarget,
            );
            return (
              <li key={suggestion.name} className="ai-suggestion-item">
                <button
                  type="button"
                  className="chip"
                  aria-pressed={selected}
                  onClick={() => criteria.toggleCriterion(suggestion.name)}
                  disabled={!selected && criteria.reachedMaxCriteria}
                >
                  {suggestion.name}
                </button>
                <p className="ai-suggestion-item__reason">{suggestion.reason}</p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
