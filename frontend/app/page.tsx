"use client";

import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/Button";
import { CriterionChip } from "@/components/CriterionChip";
import { CustomCriteriaChips } from "@/components/CustomCriteriaChips";
import { PageContainer } from "@/components/PageContainer";
import { SuggestPointsPanel } from "@/components/SuggestPointsPanel";
import { UseCaseInput } from "@/components/UseCaseInput";
import { useCriteriaSelection } from "@/hooks/useCriteriaSelection";
import { createResearch } from "@/lib/api";
import { findTechnologyIdByName, getUseCaseExamples } from "@/lib/catalog";
import { CRITERION_OPTIONS, DEFAULT_CRITERIA, MAX_CRITERIA, MIN_CRITERIA } from "@/lib/criteria";
import { CATEGORIES } from "@/data/categories";
import { TECHNOLOGY_PAIR_EXAMPLES } from "@/data/technologyPairExamples";

// Exploreのhover previewに出す代表カテゴリ。実際に技術データを持つ
// (`available: true`)カテゴリだけを見せる(Coming soonのカテゴリは
// Exploreしても中身が無いため、期待外れな誘導を避ける)。
const EXPLORE_PREVIEW_CATEGORIES = CATEGORIES.filter((c) => c.available)
  .map((c) => c.name)
  .join(" · ");

/**
 * Home(Phase 5C Finishing 追補v4)。
 *
 * 初期状態はLearn(旧Explore)/Compareという2つの同格の入口だけを見せ、
 * 説明文は追加しない。Compareは実際にクリックするまでフォームを展開しない
 * (`compareExpanded`)。Learn/Compare双方にdesktop限定のhover/focus
 * preview(CSSのみ、`app/globals.css`の`.home-entry__preview`)を持たせる。
 * Learnのリンク先は引き続き`/explore`(Technology Map)。
 */
export default function NewResearchPage() {
  const router = useRouter();
  const [compareExpanded, setCompareExpanded] = useState(false);
  const [itemA, setItemA] = useState("");
  const [itemB, setItemB] = useState("");
  const [pairExampleIndex, setPairExampleIndex] = useState(0);
  const [goal, setGoal] = useState("");
  const criteriaSelection = useCriteriaSelection(DEFAULT_CRITERIA);
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
  const [error, setError] = useState<string | null>(null);

  // 固定候補(CRITERION_OPTIONS)のラベルをそのままBase Pointの値として使う
  // (Compare SetupのBase Pointsと同じく「表示ラベル=送信する値」。
  // lib/criteria.ts参照)。
  const basePointLabels = useMemo(() => CRITERION_OPTIONS.map((option) => option.label), []);

  // Technology A/Bがcatalogの技術名と一致すれば、そのペア固有のUse Case
  // Examplesを、一致しなければ汎用exampleを使う(API呼び出しなし)。
  const useCaseExamples = useMemo(() => {
    const idA = findTechnologyIdByName(itemA);
    const idB = findTechnologyIdByName(itemB);
    return getUseCaseExamples(idA, idB);
  }, [itemA, itemB]);

  // 固定候補以外(自由入力で追加したもの)を表示用に分けておく。
  const customChips = criteria.filter(
    (c) => !CRITERION_OPTIONS.some((option) => option.label === c),
  );

  /**
   * Technology A/Bの"↗ Example comparison"。クリックするたびにcurated pairを
   * 1件ずつ順送りする(APIは呼ばない静的data、`data/technologyPairExamples.ts`)。
   *
   * 安全策: 「A/Bが両方とも空」または「A/Bとも直前に採用したペアと完全一致」の
   * ときだけ次のペアへ進める。ユーザーがA/Bのどちらか片方でも自分で書き換えて
   * いたら(部分一致・不一致どちらでも)何もしない=既存の入力を絶対に消さない。
   */
  function handleExampleComparisonClick() {
    const currentPairExample = TECHNOLOGY_PAIR_EXAMPLES[pairExampleIndex];
    const bothEmpty = itemA === "" && itemB === "";
    const matchesCurrent =
      itemA === currentPairExample.itemA && itemB === currentPairExample.itemB;
    if (!bothEmpty && !matchesCurrent) return;

    const nextIndex = bothEmpty
      ? pairExampleIndex
      : (pairExampleIndex + 1) % TECHNOLOGY_PAIR_EXAMPLES.length;
    const next = TECHNOLOGY_PAIR_EXAMPLES[nextIndex];
    setPairExampleIndex(nextIndex);
    setItemA(next.itemA);
    setItemB(next.itemB);
  }

  function handleCustomInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault(); // フォーム全体の送信を防ぐ
      addCustomCriterion();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // 二重送信防止(すでに送信中なら何もしない)。
    if (isSubmitting) return;

    setError(null);

    if (criteria.length < MIN_CRITERIA) {
      setError(`項目を最低${MIN_CRITERIA}個選んでください`);
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
    <PageContainer maxWidth={560}>
      <div className="home-hero">
        <h1>TechCompare AI</h1>
        <p className="home-hero__tagline">Explore technologies. Compare what fits.</p>
      </div>

      <div className="home-entries">
        <Link href="/explore" className="home-entry">
          <span className="home-entry__title">Learn</span>
          <span className="home-entry__hint">I&apos;m not sure what to compare</span>
          <span className="home-entry__preview" aria-hidden="true">
            {EXPLORE_PREVIEW_CATEGORIES}
          </span>
        </Link>

        <button
          type="button"
          className="home-entry"
          aria-expanded={compareExpanded}
          aria-controls="compare-panel"
          onClick={() => setCompareExpanded((current) => !current)}
        >
          <span className="home-entry__title">Compare</span>
          <span className="home-entry__hint">I know what to compare</span>
          <span className="home-entry__preview" aria-hidden="true">
            Technology A · Technology B · Start comparing →
          </span>
        </button>
      </div>

      <div
        id="compare-panel"
        className={
          compareExpanded ? "compare-panel compare-panel--expanded" : "compare-panel"
        }
        inert={!compareExpanded}
      >
        <div className="compare-panel__inner">
          <form onSubmit={handleSubmit}>
            <label className="home-tech-field">
              <span className="home-tech-field__label">Technology A</span>
              <input
                value={itemA}
                onChange={(e) => setItemA(e.target.value)}
                placeholder="例: FastAPI"
                required
                disabled={isSubmitting}
              />
            </label>

            <label className="home-tech-field">
              <span className="home-tech-field__label">Technology B</span>
              <input
                value={itemB}
                onChange={(e) => setItemB(e.target.value)}
                placeholder="例: Django"
                required
                disabled={isSubmitting}
              />
            </label>

            <button
              type="button"
              className="use-case-input__example"
              onClick={handleExampleComparisonClick}
              disabled={isSubmitting}
              title="クリックするたびに比較例を切り替え"
              style={{ display: "block", marginBottom: "var(--space-4)" }}
            >
              ↗ Example comparison
            </button>

            <label>
              What are you building?
              <UseCaseInput
                value={goal}
                onChange={setGoal}
                examples={useCaseExamples}
                placeholder="例: AIアプリのバックエンドとして比較したい"
                disabled={isSubmitting}
              />
            </label>

            <div style={{ marginBottom: "var(--space-5)" }}>
              <p className="compare-panel__section-label">
                Base Points · {criteria.length}/{MAX_CRITERIA}
              </p>

              <div className="chip-group" role="group" aria-label="Base Points">
                {CRITERION_OPTIONS.map((option) => {
                  const selected = criteria.some((c) => c === option.label);
                  return (
                    <CriterionChip
                      key={option.label}
                      label={option.label}
                      selected={selected}
                      onToggle={() => toggleCriterion(option.label)}
                      disabled={isSubmitting || (!selected && reachedMaxCriteria)}
                      description={option.description}
                    />
                  );
                })}
              </div>

              <CustomCriteriaChips
                chips={customChips}
                onRemove={toggleCriterion}
                disabled={isSubmitting}
              />
            </div>

            <SuggestPointsPanel
              itemA={itemA}
              itemB={itemB}
              goal={goal}
              basePoints={basePointLabels}
              criteria={criteriaSelection}
            />

            <div style={{ margin: "var(--space-5) 0" }}>
              <p className="compare-panel__section-label">Custom</p>
              <div
                style={{
                  display: "flex",
                  gap: "var(--space-2)",
                  marginTop: "var(--space-2)",
                }}
              >
                <input
                  value={customInput}
                  onChange={(e) => setCustomInput(e.target.value)}
                  onKeyDown={handleCustomInputKeyDown}
                  placeholder="追加する項目"
                  title="Enterで追加"
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
                  style={{
                    color: "var(--color-danger)",
                    fontSize: "0.82rem",
                    marginTop: "var(--space-2)",
                  }}
                >
                  {criteriaError}
                </p>
              )}
            </div>

            {error && (
              <p style={{ color: "var(--color-danger)", marginBottom: "var(--space-4)" }}>
                {error}
              </p>
            )}

            <Button type="submit" loading={isSubmitting}>
              Start Research
            </Button>
          </form>
        </div>
      </div>
    </PageContainer>
  );
}
