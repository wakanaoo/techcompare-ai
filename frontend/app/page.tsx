"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { createResearch } from "@/lib/api";
import {
  CRITERION_OPTIONS,
  DEFAULT_CRITERIA,
  MAX_CRITERIA,
  MIN_CRITERIA,
} from "@/lib/criteria";

export default function NewResearchPage() {
  const router = useRouter();
  const [itemA, setItemA] = useState("");
  const [itemB, setItemB] = useState("");
  const [goal, setGoal] = useState("");
  const [criteria, setCriteria] = useState<string[]>(DEFAULT_CRITERIA);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleCriterion(key: string) {
    setCriteria((current) => {
      if (current.includes(key)) {
        return current.filter((c) => c !== key);
      }
      if (current.length >= MAX_CRITERIA) {
        return current;
      }
      return [...current, key];
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (criteria.length < MIN_CRITERIA) {
      setError(`比較軸を最低${MIN_CRITERIA}個選んでください`);
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

  return (
    <main style={{ maxWidth: 560, margin: "0 auto", padding: "2rem 1rem" }}>
      <h1>TechCompare AI</h1>
      <p style={{ marginBottom: "1.5rem" }}>
        比較したい2つの技術と、比較したい目的・比較軸を選んでください。
      </p>

      <form onSubmit={handleSubmit}>
        <label>
          技術A
          <input
            value={itemA}
            onChange={(e) => setItemA(e.target.value)}
            placeholder="例: FastAPI"
            required
          />
        </label>

        <label>
          技術B
          <input
            value={itemB}
            onChange={(e) => setItemB(e.target.value)}
            placeholder="例: Django"
            required
          />
        </label>

        <label>
          目的
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="例: AIアプリのバックエンドとして比較したい"
            required
          />
        </label>

        <fieldset style={{ border: "1px solid #888", borderRadius: 4, marginBottom: "1rem", padding: "0.75rem" }}>
          <legend>
            比較軸({MIN_CRITERIA}〜{MAX_CRITERIA}個、現在{criteria.length}個選択中)
          </legend>
          {CRITERION_OPTIONS.map((option) => (
            <label
              key={option.key}
              style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}
            >
              <input
                type="checkbox"
                checked={criteria.includes(option.key)}
                onChange={() => toggleCriterion(option.key)}
                style={{ width: "auto" }}
              />
              {option.label}
            </label>
          ))}
        </fieldset>

        {error && <p style={{ color: "crimson" }}>{error}</p>}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "作成中..." : "Start Research"}
        </button>
      </form>
    </main>
  );
}
