"use client";

import { useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { CriterionChip } from "@/components/CriterionChip";
import { CustomCriteriaChips } from "@/components/CustomCriteriaChips";
import { PageContainer } from "@/components/PageContainer";
import { SuggestPointsPanel } from "@/components/SuggestPointsPanel";
import { UseCaseInput } from "@/components/UseCaseInput";
import { useCriteriaSelection } from "@/hooks/useCriteriaSelection";
import { createResearch } from "@/lib/api";
import {
  getBaseComparisonCriteria,
  getBasePointDescription,
  getRelation,
  getTechnology,
  getUseCaseExamples,
} from "@/lib/catalog";
import { MAX_CRITERIA, MIN_CRITERIA, canonicalCriterionKey } from "@/lib/criteria";

/**
 * Compare Setup(Phase 5C)。
 *
 * Explore経由(Technology DetailのCommon Comparisons)から到達し、最終的には
 * 既存Research作成フロー(createResearch → /research/[id])へ合流する。
 * item A/Bの順序は「Technology Detailで見ていた技術がitem_a、選んだ比較先が
 * item_b」で統一する(Common Comparisonsのリンク生成側で保証済み)。
 *
 * State受け渡しはURLのpath params(technology id)とこのページ内の
 * ローカルstateのみで完結させる(グローバルstore/Contextは導入しない)。
 */
export default function CompareSetupPage() {
  const params = useParams<{ itemA: string; itemB: string }>();
  const router = useRouter();

  const techA = getTechnology(params.itemA);
  const techB = getTechnology(params.itemB);

  const [goal, setGoal] = useState("");
  const criteriaSelection = useCriteriaSelection([]);
  const {
    criteria,
    customInput,
    setCustomInput,
    criteriaError,
    toggleCriterion,
    addCustomCriterion,
    reachedMaxCriteria,
  } = criteriaSelection;
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (!techA || !techB) {
    return (
      <PageContainer maxWidth={640}>
        <Alert
          tone="danger"
          title="Technologyが見つかりません"
          details="指定されたTechnologyの組み合わせが見つかりません。"
        />
        <div style={{ marginTop: "var(--space-4)" }}>
          <Link href="/explore" style={{ color: "var(--color-accent)", fontWeight: 600 }}>
            ← Explore Technologiesに戻る
          </Link>
        </div>
      </PageContainer>
    );
  }

  const relation = getRelation(techA.id, techB.id);
  const basePoints = getBaseComparisonCriteria(techA.id, techB.id);
  // getUseCaseExamples()はcatalogの静的dataからそのまま配列を返すため、
  // 同じidの組み合わせであれば呼び出しごとに同じ参照になる
  // (UseCaseInputの循環位置リセット用useEffectの依存配列として安全)。
  const useCaseExamples = getUseCaseExamples(techA.id, techB.id);
  // handleStartResearch()はクロージャなので、TypeScriptはtechA/techBの
  // 「undefinedではない」narrowingをその中まで持ち越さない。plain stringとして
  // 捕まえておくことで、closure内でのnullチェックを不要にする。
  const itemAName = techA.name;
  const itemBName = techB.name;
  // Base Points(catalog由来の固定候補)以外(自由入力・AI提案経由で追加した
  // もの)を、Homeと同じ`CustomCriteriaChips`で表示するために分けておく。
  const customChips = criteria.filter(
    (c) => !basePoints.some((point) => canonicalCriterionKey(point) === canonicalCriterionKey(c)),
  );

  function handleCustomInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      addCustomCriterion();
    }
  }

  async function handleStartResearch() {
    if (isSubmitting) return;

    setSubmitError(null);

    if (!goal.trim()) {
      setSubmitError("Use Caseを入力してください");
      return;
    }
    if (criteria.length < MIN_CRITERIA) {
      setSubmitError(`項目を最低${MIN_CRITERIA}個選んでください`);
      return;
    }

    setIsSubmitting(true);
    try {
      const research = await createResearch({
        item_a: itemAName,
        item_b: itemBName,
        goal: goal.trim(),
        criteria,
      });
      router.push(`/research/${research.id}`);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "予期しないエラーが発生しました",
      );
      setIsSubmitting(false);
    }
  }

  return (
    <PageContainer maxWidth={640}>
      <Link
        href={`/explore/technology/${techA.id}`}
        style={{
          display: "inline-block",
          fontSize: "0.85rem",
          fontWeight: 600,
          color: "var(--color-accent)",
          marginBottom: "var(--space-4)",
        }}
      >
        ← {techA.name}
      </Link>

      <Card style={{ marginBottom: "var(--space-4)" }}>
        <div className="compare-setup__vs">
          <div className="compare-setup__side">
            <p className="compare-setup__side-name">{techA.name}</p>
            <Badge tone="neutral">{techA.subcategory}</Badge>
          </div>
          <span className="compare-setup__vs-label">VS</span>
          <div className="compare-setup__side">
            <p className="compare-setup__side-name">{techB.name}</p>
            <Badge tone="neutral">{techB.subcategory}</Badge>
          </div>
        </div>

        {relation?.relationSummary && (
          <div style={{ marginTop: "var(--space-4)" }}>
            <p className="evidence-detail__section-label">HOW ARE THEY RELATED?</p>
            <p style={{ color: "var(--color-text-muted)" }}>{relation.relationSummary}</p>
          </div>
        )}
      </Card>

      <Card style={{ marginBottom: "var(--space-4)" }}>
        <label>
          What are you building?
          <UseCaseInput
            value={goal}
            onChange={setGoal}
            examples={useCaseExamples}
            placeholder="例: SNS投稿を大量保存したい"
            disabled={isSubmitting}
          />
        </label>
      </Card>

      <Card style={{ marginBottom: "var(--space-4)" }}>
        <p
          style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "var(--space-2)" }}
        >
          Base Points · {criteria.length}/{MAX_CRITERIA}
        </p>
        <div className="chip-group" role="group" aria-label="Base Points">
          {basePoints.map((point) => {
            const selected = criteria.some(
              (c) => canonicalCriterionKey(c) === canonicalCriterionKey(point),
            );
            return (
              <CriterionChip
                key={point}
                label={point}
                selected={selected}
                onToggle={() => toggleCriterion(point)}
                disabled={isSubmitting || (!selected && reachedMaxCriteria)}
                description={getBasePointDescription(point)}
              />
            );
          })}
        </div>

        <CustomCriteriaChips
          chips={customChips}
          onRemove={toggleCriterion}
          disabled={isSubmitting}
        />
      </Card>

      <Card style={{ marginBottom: "var(--space-4)" }}>
        <SuggestPointsPanel
          itemA={itemAName}
          itemB={itemBName}
          goal={goal}
          basePoints={basePoints}
          criteria={criteriaSelection}
        />
      </Card>

      <Card style={{ marginBottom: "var(--space-4)" }}>
        <p className="evidence-detail__section-label">Custom</p>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
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
            style={{ color: "var(--color-danger)", fontSize: "0.82rem", marginTop: "var(--space-2)" }}
          >
            {criteriaError}
          </p>
        )}
      </Card>

      {submitError && (
        <p style={{ color: "var(--color-danger)", marginBottom: "var(--space-4)" }}>
          {submitError}
        </p>
      )}

      <Button onClick={handleStartResearch} loading={isSubmitting}>
        Start Research
      </Button>
    </PageContainer>
  );
}
