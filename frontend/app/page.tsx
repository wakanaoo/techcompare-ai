"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { createResearch } from "@/lib/api";

export default function NewResearchPage() {
  const router = useRouter();
  const [itemA, setItemA] = useState("");
  const [itemB, setItemB] = useState("");
  const [goal, setGoal] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const research = await createResearch({
        item_a: itemA,
        item_b: itemB,
        goal,
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
    <main style={{ maxWidth: 480, margin: "0 auto", padding: "2rem 1rem" }}>
      <h1>TechCompare AI</h1>
      <p style={{ marginBottom: "1.5rem" }}>
        比較したい2つの技術と、比較したい目的を入力してください。
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

        {error && <p style={{ color: "crimson" }}>{error}</p>}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "作成中..." : "Start Research"}
        </button>
      </form>
    </main>
  );
}
