"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { getResearch, type Research } from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

const STATUS_LABEL: Record<Research["status"], string> = {
  pending: "○ 待機中",
  researching: "● 比較を生成中...",
  completed: "✓ 完了",
  failed: "✗ 失敗",
};

export default function ResearchProgressPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [research, setResearch] = useState<Research | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const hasRedirected = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const data = await getResearch(params.id);
        if (cancelled) return;

        setResearch(data);
        setIsLoading(false);

        if (data.status === "completed") {
          if (!hasRedirected.current) {
            hasRedirected.current = true;
            router.push(`/research/${params.id}/result`);
          }
          return;
        }

        if (data.status === "failed") {
          return; // これ以上pollingしない。エラー表示のみ。
        }

        // pending / researching の間は数秒おきに再取得する。
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "予期しないエラーが発生しました",
          );
          setIsLoading(false);
        }
      }
    }

    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [params.id, router]);

  return (
    <main style={{ maxWidth: 480, margin: "0 auto", padding: "2rem 1rem" }}>
      <h1>Research Progress</h1>

      {isLoading && <p>読み込み中...</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {research && (
        <>
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
            <dd>{STATUS_LABEL[research.status]}</dd>
          </dl>

          {research.status === "failed" && (
            <p style={{ color: "crimson", marginTop: "1rem" }}>
              エラー: {research.error_message ?? "不明なエラーが発生しました"}
            </p>
          )}
        </>
      )}
    </main>
  );
}
