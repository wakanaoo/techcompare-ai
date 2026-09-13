"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { PageContainer } from "@/components/PageContainer";
import { createResearch } from "@/lib/api";
import {
  CRITERION_OPTIONS,
  DEFAULT_CRITERIA,
  MAX_CRITERIA,
  MAX_CRITERION_LENGTH,
  MIN_CRITERIA,
  canonicalCriterionKey,
} from "@/lib/criteria";

export default function NewResearchPage() {
  const router = useRouter();
  const [itemA, setItemA] = useState("");
  const [itemB, setItemB] = useState("");
  const [goal, setGoal] = useState("");
  const [criteria, setCriteria] = useState<string[]>(DEFAULT_CRITERIA);
  const [customInput, setCustomInput] = useState("");
  const [criteriaError, setCriteriaError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 「候補」チップ以外(自由入力で追加したもの)を表示用に分けておく。
  const customChips = criteria.filter(
    (c) => !CRITERION_OPTIONS.some((option) => option.key === c),
  );

  function toggleCriterion(key: string) {
    // canonicalCriterionKey()で正規化した上で照合する。固定候補のkeyと、
    // それに対応するlabelを自由入力で追加した場合が同一視され、
    // どちらの経路からでも二重に追加されないようにする。
    const canonicalTarget = canonicalCriterionKey(key);

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
      return [...current, key];
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

  function handleCustomInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault(); // フォーム全体の送信を防ぐ
      addCustomCriterion();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // 二重送信防止(すでに送信中なら何もしない)。
    if (isSubmitting) return;

    setError(null);

    if (criteria.length < MIN_CRITERIA) {
      setError(`項目を最低${MIN_CRITERIA}個選んでください`);
      return;
    }

    setIsSubmitting(true);

    try {
      const research = await createResearch({
        item_a: itemA,
        item_b: itemB,
        goal,
        criteria,
      });
      router.push(`/research/${research.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "予期しないエラーが発生しました",
      );
      setIsSubmitting(false);
    }
  }

  const reachedMaxCriteria = criteria.length >= MAX_CRITERIA;

  return (
    <PageContainer maxWidth={560}>
      <div style={{ marginBottom: "var(--space-5)" }}>
        <h1>Compare Technologies</h1>
        <p style={{ color: "var(--color-text-muted)", marginTop: "var(--space-2)" }}>
          2つの技術と利用シーンを入力すると、Web上の情報をもとに比較・分析します。
        </p>
      </div>

      <Card>
        <form onSubmit={handleSubmit}>
          <label>
            Technology A
            <input
              value={itemA}
              onChange={(e) => setItemA(e.target.value)}
              placeholder="例: FastAPI"
              required
              disabled={isSubmitting}
            />
          </label>

          <label>
            Technology B
            <input
              value={itemB}
              onChange={(e) => setItemB(e.target.value)}
              placeholder="例: Django"
              required
              disabled={isSubmitting}
            />
          </label>

          <label>
            利用シーン
            <input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="例: AIアプリのバックエンドとして比較したい"
              required
              disabled={isSubmitting}
            />
          </label>

          <div style={{ marginBottom: "var(--space-5)" }}>
            <p
              style={{
                fontSize: "0.9rem",
                fontWeight: 600,
                marginBottom: "var(--space-2)",
              }}
            >
              比較したいポイント({criteria.length} / {MAX_CRITERIA} 選択中)
            </p>
            <p
              style={{
                fontSize: "0.82rem",
                color: "var(--color-text-muted)",
                marginBottom: "var(--space-3)",
              }}
            >
              候補から選ぶか、自由に項目を追加できます。
            </p>

            <p
              style={{
                fontSize: "0.78rem",
                color: "var(--color-text-subtle)",
                marginBottom: "var(--space-1)",
              }}
            >
              候補
            </p>
            <div className="chip-group" role="group" aria-label="候補の項目">
              {CRITERION_OPTIONS.map((option) => {
                const selected = criteria.some(
                  (c) => canonicalCriterionKey(c) === canonicalCriterionKey(option.key),
                );
                return (
                  <button
                    key={option.key}
                    type="button"
                    className="chip"
                    aria-pressed={selected}
                    onClick={() => toggleCriterion(option.key)}
                    disabled={isSubmitting || (!selected && reachedMaxCriteria)}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>

            {customChips.length > 0 && (
              <>
                <p
                  style={{
                    fontSize: "0.78rem",
                    color: "var(--color-text-subtle)",
                    marginTop: "var(--space-3)",
                    marginBottom: "var(--space-1)",
                  }}
                >
                  追加した項目
                </p>
                <div className="chip-group" role="group" aria-label="追加した項目">
                  {customChips.map((text) => (
                    <button
                      key={text}
                      type="button"
                      className="chip"
                      aria-pressed="true"
                      onClick={() => toggleCriterion(text)}
                      disabled={isSubmitting}
                      title="クリックして削除"
                    >
                      {text} ✕
                    </button>
                  ))}
                </div>
              </>
            )}

            <div
              style={{
                display: "flex",
                gap: "var(--space-2)",
                marginTop: "var(--space-3)",
              }}
            >
              <input
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value)}
                onKeyDown={handleCustomInputKeyDown}
                placeholder="例：検索の柔軟性(Enterで追加)"
                disabled={isSubmitting || reachedMaxCriteria}
                style={{ flex: 1, marginBottom: 0 }}
              />
              <Button
                type="button"
                variant="secondary"
                onClick={addCustomCriterion}
                disabled={isSubmitting || reachedMaxCriteria}
              >
                追加
              </Button>
            </div>

            {criteriaError && (
              <p
                style={{
                  color: "var(--color-danger)",
                  fontSize: "0.82rem",
                  marginTop: "var(--space-2)",
                }}
              >
                {criteriaError}
              </p>
            )}
          </div>

          {error && (
            <p style={{ color: "var(--color-danger)", marginBottom: "var(--space-4)" }}>
              {error}
            </p>
          )}

          <Button type="submit" loading={isSubmitting}>
            Start Research
          </Button>
        </form>
      </Card>
    </PageContainer>
  );
}
