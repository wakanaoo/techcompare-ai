"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { EvidenceLinks } from "@/components/EvidenceLinks";
import { PageContainer } from "@/components/PageContainer";
import { ScoreDots } from "@/components/ScoreDots";
import {
  getResearchResult,
  type ComparisonRow,
  type ResearchResult,
  type Side,
  type Winner,
} from "@/lib/api";

/** Comparison表・Resultバッジ用の短いラベル("Tie"はそのまま表示する)。 */
function winnerLabel(winner: Winner, itemA: string, itemB: string): string {
  if (winner === "item_a") return itemA;
  if (winner === "item_b") return itemB;
  return "Tie";
}

/** Recommendationカードの見出し用(tieの場合はより自然な言い回しにする)。 */
function recommendationHeadline(winner: Winner, itemA: string, itemB: string): string {
  if (winner === "item_a") return itemA;
  if (winner === "item_b") return itemB;
  return "No clear winner";
}

function winnerBadgeTone(winner: Winner): "info" | "neutral" {
  return winner === "tie" ? "neutral" : "info";
}

function evidenceForSide(row: ComparisonRow, side: Side) {
  return row.evidence.filter((e) => e.side === side);
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
    <PageContainer maxWidth={880}>
      {!result && <h1>Comparison Report</h1>}

      {isLoading && (
        <Card style={{ marginTop: "var(--space-4)" }}>
          <p style={{ color: "var(--color-text-muted)" }}>読み込み中…</p>
        </Card>
      )}

      {error && (
        <Alert tone="danger" title="比較結果の取得に失敗しました" details={error} />
      )}

      {result && (
        <>
          <div style={{ marginBottom: "var(--space-6)" }}>
            <p className="report-header__eyebrow">Comparison Report</p>
            <h1 className="report-header__title">
              {result.item_a} vs {result.item_b}
            </h1>
            <div className="report-header__usecase">
              <span className="report-header__usecase-label">Use case</span>
              <span className="report-header__usecase-text">{result.goal}</span>
            </div>
          </div>

          <Card style={{ marginBottom: "var(--space-6)" }}>
            <p className="recommendation__label">Recommendation</p>
            <p className="recommendation__winner">
              {recommendationHeadline(result.recommendation.winner, result.item_a, result.item_b)}
            </p>
            <p className="recommendation__summary">{result.recommendation.summary}</p>
            <p className="recommendation__why-label">Why</p>
            <p className="recommendation__reason">{result.recommendation.reason}</p>
          </Card>

          <h2 style={{ marginBottom: "var(--space-3)" }}>Comparison</h2>

          {/* デスクトップ: table。狭い画面ではCSSでcriterionごとのcardへ切り替える。 */}
          <div className="comparison-table-wrapper" style={{ overflowX: "auto" }}>
            <table className="comparison-table">
              <thead>
                <tr>
                  <th className="comparison-table__criterion-col">Point</th>
                  <th>{result.item_a}</th>
                  <th>{result.item_b}</th>
                  <th className="comparison-table__result-col">Result</th>
                </tr>
              </thead>
              <tbody>
                {result.comparisons.map((row) => (
                  <tr key={row.criterion}>
                    <td className="comparison-table__criterion-col">
                      {row.criterion_label}
                    </td>
                    <td>
                      <p className="comparison-table__item-summary">{row.item_a_summary}</p>
                      <ScoreDots score={row.item_a_score} />
                      <div style={{ marginTop: "var(--space-2)" }}>
                        <EvidenceLinks evidence={evidenceForSide(row, "item_a")} />
                      </div>
                    </td>
                    <td>
                      <p className="comparison-table__item-summary">{row.item_b_summary}</p>
                      <ScoreDots score={row.item_b_score} />
                      <div style={{ marginTop: "var(--space-2)" }}>
                        <EvidenceLinks evidence={evidenceForSide(row, "item_b")} />
                      </div>
                    </td>
                    <td className="comparison-table__result-col">
                      <Badge tone={winnerBadgeTone(row.winner)}>
                        {winnerLabel(row.winner, result.item_a, result.item_b)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="comparison-cards">
            {result.comparisons.map((row) => (
              <Card key={row.criterion}>
                <div className="comparison-card__header">
                  <span style={{ fontWeight: 700 }}>{row.criterion_label}</span>
                  <Badge tone={winnerBadgeTone(row.winner)}>
                    {winnerLabel(row.winner, result.item_a, result.item_b)}
                  </Badge>
                </div>

                <div className="comparison-card__side">
                  <p className="comparison-card__side-name">{result.item_a}</p>
                  <p className="comparison-table__item-summary">{row.item_a_summary}</p>
                  <ScoreDots score={row.item_a_score} />
                  <div style={{ marginTop: "var(--space-2)" }}>
                    <EvidenceLinks evidence={evidenceForSide(row, "item_a")} />
                  </div>
                </div>

                <div className="comparison-card__side">
                  <p className="comparison-card__side-name">{result.item_b}</p>
                  <p className="comparison-table__item-summary">{row.item_b_summary}</p>
                  <ScoreDots score={row.item_b_score} />
                  <div style={{ marginTop: "var(--space-2)" }}>
                    <EvidenceLinks evidence={evidenceForSide(row, "item_b")} />
                  </div>
                </div>
              </Card>
            ))}
          </div>

          <h2 style={{ marginTop: "var(--space-6)", marginBottom: "var(--space-3)" }}>
            Sources
          </h2>
          {result.sources.length === 0 ? (
            <p style={{ color: "var(--color-text-muted)" }}>
              参照できる情報源が見つかりませんでした。
            </p>
          ) : (
            <ul
              style={{
                listStyle: "none",
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-2)",
              }}
            >
              {result.sources.map((source) => (
                <li key={source.id}>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "var(--color-accent)", fontSize: "0.92rem" }}
                  >
                    {source.title}
                  </a>
                </li>
              ))}
            </ul>
          )}

          <p
            style={{
              marginTop: "var(--space-6)",
              fontSize: "0.85rem",
              color: "var(--color-text-subtle)",
              borderTop: "1px solid var(--color-border)",
              paddingTop: "var(--space-4)",
            }}
          >
            比較結果は上記の情報源に基づいてLLMが生成したものです。情報源に
            明確な記載がない場合は、その旨をLLMが明示するよう設計していますが、
            内容の正確性は必ず元の情報源(上記リンク)でもご確認ください。
          </p>
        </>
      )}
    </PageContainer>
  );
}
