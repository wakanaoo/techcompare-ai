"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { getResearchResult, type ResearchResult, type Winner } from "@/lib/api";

function winnerLabel(winner: Winner, itemA: string, itemB: string): string {
  if (winner === "item_a") return itemA;
  if (winner === "item_b") return itemB;
  return "引き分け";
}

export default function ComparisonReportPage() {
  const params = useParams<{ id: string }>();
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await getResearchResult(params.id);
        if (!cancelled) setResult(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "予期しないエラーが発生しました",
          );
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "2rem 1rem" }}>
      <h1>Comparison Report</h1>

      {isLoading && <p>読み込み中...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {result && (
        <>
          <p style={{ fontSize: "1.1rem", fontWeight: "bold" }}>
            {result.item_a} vs {result.item_b}
          </p>
          <p style={{ marginBottom: "1.5rem" }}>目的: {result.goal}</p>

          <section
            style={{
              border: "1px solid #888",
              borderRadius: 6,
              padding: "1rem",
              marginBottom: "1.5rem",
            }}
          >
            <h2 style={{ marginBottom: "0.5rem" }}>Recommendation</h2>
            <p>
              <strong>推奨:</strong>{" "}
              {winnerLabel(result.recommendation.winner, result.item_a, result.item_b)}
            </p>
            <p>{result.recommendation.summary}</p>
            <p style={{ marginTop: "0.5rem", opacity: 0.85 }}>
              理由: {result.recommendation.reason}
            </p>
          </section>

          <h2 style={{ marginBottom: "0.5rem" }}>比較表</h2>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>
                  <th style={cellStyle}>比較軸</th>
                  <th style={cellStyle}>{result.item_a}</th>
                  <th style={cellStyle}>{result.item_b}</th>
                  <th style={cellStyle}>優位</th>
                </tr>
              </thead>
              <tbody>
                {result.comparisons.map((row) => (
                  <tr key={row.criterion}>
                    <td style={cellStyle}>{row.criterion_label}</td>
                    <td style={cellStyle}>
                      {row.item_a_summary}
                      <br />
                      <strong>スコア: {row.item_a_score}/5</strong>
                    </td>
                    <td style={cellStyle}>
                      {row.item_b_summary}
                      <br />
                      <strong>スコア: {row.item_b_score}/5</strong>
                    </td>
                    <td style={cellStyle}>
                      {winnerLabel(row.winner, result.item_a, result.item_b)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p
            style={{
              marginTop: "1.5rem",
              fontSize: "0.85rem",
              opacity: 0.7,
              borderTop: "1px solid #888",
              paddingTop: "0.75rem",
            }}
          >
            現在の比較はLLM知識をもとに生成されており、外部情報源による検証はPhase 3で追加予定です。
          </p>
        </>
      )}
    </main>
  );
}

const cellStyle: React.CSSProperties = {
  border: "1px solid #888",
  padding: "0.5rem",
  textAlign: "left",
  verticalAlign: "top",
};
