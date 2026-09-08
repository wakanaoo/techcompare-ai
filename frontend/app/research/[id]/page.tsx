"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { getResearch, type Research } from "@/lib/api";

export default function ResearchProgressPage() {
  const params = useParams<{ id: string }>();
  const [research, setResearch] = useState<Research | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await getResearch(params.id);
        if (!cancelled) setResearch(data);
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
    <main style={{ maxWidth: 480, margin: "0 auto", padding: "2rem 1rem" }}>
      <h1>Research Progress</h1>

      {isLoading && <p>読み込み中...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {research && (
        <dl>
          <dt>Research ID</dt>
          <dd>{research.id}</dd>

          <dt>技術A</dt>
          <dd>{research.item_a}</dd>

          <dt>技術B</dt>
          <dd>{research.item_b}</dd>

          <dt>目的</dt>
          <dd>{research.goal}</dd>

          <dt>Status</dt>
          <dd>{research.status}</dd>
        </dl>
      )}

      {/*
        Phase 1ではBackgroundでのResearch処理をまだ実装していないため、
        statusは基本的に "pending" のまま変化しない。
        自動ポーリングによる状態更新は次のVertical Sliceで追加する。
      */}
    </main>
  );
}
