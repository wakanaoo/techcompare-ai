"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { Alert } from "@/components/Alert";
import { Card } from "@/components/Card";
import { PageContainer } from "@/components/PageContainer";
import { getEvidence, type EvidenceDetail } from "@/lib/api";

export default function EvidenceViewerPage() {
  const params = useParams<{ id: string }>();
  const [evidence, setEvidence] = useState<EvidenceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await getEvidence(params.id);
        if (!cancelled) setEvidence(data);
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
    <PageContainer maxWidth={640}>
      {evidence && (
        <Link
          href={`/research/${evidence.research_id}/result`}
          style={{
            display: "inline-block",
            fontSize: "0.85rem",
            fontWeight: 600,
            color: "var(--color-accent)",
            marginBottom: "var(--space-4)",
          }}
        >
          ← Back to Report
        </Link>
      )}

      <h1>Evidence</h1>

      {isLoading && (
        <Card style={{ marginTop: "var(--space-4)" }}>
          <p style={{ color: "var(--color-text-muted)" }}>読み込み中…</p>
        </Card>
      )}

      {error && (
        <Alert tone="danger" title="Evidenceの取得に失敗しました" details={error} />
      )}

      {evidence && (
        <>
          <p
            style={{
              color: "var(--color-text-muted)",
              margin: "var(--space-2) 0 var(--space-5)",
            }}
          >
            <strong style={{ color: "var(--color-text)" }}>{evidence.side_label}</strong>
            {" · "}
            {evidence.criterion_label}
          </p>

          <Card style={{ marginBottom: "var(--space-4)" }}>
            <p className="evidence-detail__section-label">Source</p>
            <a
              href={evidence.source_url}
              target="_blank"
              rel="noreferrer"
              style={{ fontWeight: 700, color: "var(--color-accent)" }}
            >
              {evidence.source_title}
            </a>
            <p
              style={{
                marginTop: "var(--space-1)",
                fontSize: "0.8rem",
                color: "var(--color-text-subtle)",
                wordBreak: "break-all",
              }}
            >
              {evidence.source_url}
            </p>
          </Card>

          <Card>
            <p className="evidence-detail__section-label">Source excerpt</p>
            <p className="evidence-detail__quote">{evidence.evidence_text}</p>
          </Card>

          <p
            style={{
              marginTop: "var(--space-5)",
              fontSize: "0.85rem",
              color: "var(--color-text-subtle)",
            }}
          >
            この根拠本文はLLMが生成したものではなく、Web検索(Tavily API)で
            実際に取得した情報源の本文をそのまま表示しています。
          </p>
        </>
      )}
    </PageContainer>
  );
}
