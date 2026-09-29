"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { PageContainer } from "@/components/PageContainer";
import { useElapsedSeconds } from "@/hooks/useElapsedSeconds";
import { createResearch, getResearch, type Research } from "@/lib/api";
import { getFriendlyErrorMessage } from "@/lib/errorMessages";

const POLL_INTERVAL_MS = 2000;

// completed検知後、router.push()による自動遷移が何らかの理由で完了しない
// ケース(例: dev serverのHMR干渉、ネットワークの瞬断)に備えて、この秒数
// 経ってもこの画面に残っていた場合だけ、手動遷移用の「View Report」ボタンを
// 表示する。正常に即時遷移できた場合は、このタイマーが発火する前に
// コンポーネント自体がunmountされるため、fallback UIは実質見えない。
const NAVIGATION_FALLBACK_DELAY_MS = 4000;

const STATUS_DESCRIPTION: Record<Research["status"], string> = {
  pending: "調査を開始しています。",
  researching: "Web情報を収集・分析し、比較結果を生成しています。",
  completed: "調査完了。結果画面に移動します…",
  failed: "調査を完了できませんでした。",
};

export default function ResearchProgressPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [research, setResearch] = useState<Research | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [showViewReportFallback, setShowViewReportFallback] = useState(false);
  const hasRedirected = useRef(false);

  // 別のResearch ID(例: 「もう一度試す」からの遷移)に切り替わった際、前の
  // Researchの内容が一瞬表示され続けないよう、render中に状態をリセットする。
  // (useEffect内でのsetStateではなく、Reactが推奨する「propが変わったら
  // render中にstateを調整する」パターン: https://react.dev/learn/you-might-not-need-an-effect)
  const [trackedId, setTrackedId] = useState(params.id);
  if (params.id !== trackedId) {
    setTrackedId(params.id);
    setResearch(null);
    setError(null);
    setIsLoading(true);
    setRetryError(null);
    setShowViewReportFallback(false);
  }

  useEffect(() => {
    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let fallbackTimer: ReturnType<typeof setTimeout> | undefined;

    // refの初期化はrender中ではなくeffect内で行う(params.id変更のたびに
    // このeffectも再実行されるため、ここでリセットすれば十分)。
    hasRedirected.current = false;

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
            // 自動遷移が完了しない場合だけのfallback(通常はunmountにより
            // このタイマーが発火する前にクリーンアップされる)。
            fallbackTimer = setTimeout(() => {
              if (!cancelled) setShowViewReportFallback(true);
            }, NAVIGATION_FALLBACK_DELAY_MS);
          }
          return;
        }

        if (data.status === "failed") {
          return; // これ以上pollingしない。エラー表示のみ。
        }

        // pending / researching の間は数秒おきに再取得する。
        pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
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
      if (pollTimer) clearTimeout(pollTimer);
      if (fallbackTimer) clearTimeout(fallbackTimer);
    };
  }, [params.id, router]);

  const isActive = research?.status === "pending" || research?.status === "researching";
  const elapsedSeconds = useElapsedSeconds(research?.created_at, isActive);

  async function handleRetry() {
    if (!research || isRetrying) return; // 二重送信防止

    setIsRetrying(true);
    setRetryError(null);

    try {
      const newResearch = await createResearch({
        item_a: research.item_a,
        item_b: research.item_b,
        goal: research.goal,
        criteria: research.criteria,
      });
      router.push(`/research/${newResearch.id}`);
    } catch (err) {
      setRetryError(
        err instanceof Error ? err.message : "再試行に失敗しました",
      );
      setIsRetrying(false);
    }
  }

  const friendlyError =
    research?.status === "failed"
      ? getFriendlyErrorMessage(research.error_message)
      : null;

  return (
    <PageContainer maxWidth={560}>
      {isLoading && <p style={{ color: "var(--color-text-muted)" }}>読み込み中…</p>}

      {error && (
        <Alert tone="danger" title="読み込みに失敗しました" details={error} />
      )}

      {research && (
        <div className="research-screen">
          <div
            className={isActive ? "research-motion" : "research-motion research-motion--static"}
            aria-hidden="true"
          >
            <span>{research.item_a}</span>
            <span className="research-motion__track">
              <span className="research-motion__dot research-motion__dot--a" />
              <span className="research-motion__dot research-motion__dot--b" />
              <span
                className="research-motion__dot research-motion__dot--a"
                style={{ animationDelay: "1.6s" }}
              />
            </span>
            <span>{research.item_b}</span>
          </div>

          <div role="status" aria-live="polite">
            {isActive && (
              <>
                <p className="research-status__label">Researching…</p>
                <p className="research-status__usecase">{research.goal}</p>
                <p className="research-status__meta">
                  {STATUS_DESCRIPTION[research.status]} · {elapsedSeconds}秒
                </p>
              </>
            )}

            {research.status === "completed" &&
              (showViewReportFallback ? (
                <div>
                  <p style={{ fontWeight: 700 }}>Research Complete</p>
                  <p className="research-status__description">レポートを準備しています…</p>
                  <div style={{ marginTop: "var(--space-3)" }}>
                    <Button href={`/research/${params.id}/result`}>View Report →</Button>
                  </div>
                </div>
              ) : (
                <p className="research-status__description">{STATUS_DESCRIPTION.completed}</p>
              ))}
          </div>

          {research.status === "failed" && friendlyError && (
            <div style={{ marginTop: "var(--space-4)", textAlign: "left" }}>
              <p className="research-status__description" style={{ textAlign: "center" }}>
                {STATUS_DESCRIPTION.failed}
              </p>
              <Alert
                tone="danger"
                title={friendlyError.headline}
                description="この調査は終了しました。"
                details={friendlyError.detail}
              />

              {retryError && (
                <p
                  style={{
                    color: "var(--color-danger)",
                    marginTop: "var(--space-3)",
                    fontSize: "0.85rem",
                  }}
                >
                  再試行にも失敗しました: {retryError}
                </p>
              )}

              <div
                style={{
                  display: "flex",
                  gap: "var(--space-3)",
                  marginTop: "var(--space-4)",
                  flexWrap: "wrap",
                }}
              >
                <Button onClick={handleRetry} loading={isRetrying}>
                  同じ条件でもう一度試す
                </Button>
                <Button href="/" variant="secondary">
                  入力画面に戻る
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </PageContainer>
  );
}
