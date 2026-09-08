"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

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
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "2rem 1rem" }}>
      <h1>Evidence Viewer</h1>

      {isLoading && <p>読み込み中...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {evidence && (
        <dl>
          <dt>比較軸</dt>
          <dd>{evidence.criterion_label}</dd>

          <dt>Claim(何についての根拠か)</dt>
          <dd>{evidence.claim}</dd>

          <dt>情報源タイトル</dt>
          <dd>{evidence.source_title}</dd>

          <dt>情報源URL</dt>
          <dd>
            <a href={evidence.source_url} target="_blank" rel="noreferrer">
              {evidence.source_url}
            </a>
          </dd>

          <dt>根拠となった本文(抜粋)</dt>
          <dd style={{ whiteSpace: "pre-wrap" }}>{evidence.evidence_text}</dd>
        </dl>
      )}

      {evidence && (
        <p style={{ marginTop: "1.5rem", fontSize: "0.85rem", opacity: 0.7 }}>
          この根拠本文はLLMが生成したものではなく、Web検索(Tavily API)で
          実際に取得した情報源の本文をそのまま表示しています。
        </p>
      )}
    </main>
  );
}
