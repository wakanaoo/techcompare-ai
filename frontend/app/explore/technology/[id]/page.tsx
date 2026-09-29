"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Alert } from "@/components/Alert";
import { ConceptPopover } from "@/components/ConceptPopover";
import { PageContainer } from "@/components/PageContainer";
import {
  getCategory,
  getCommonComparisons,
  getRelatedTechnologies,
  getTechnology,
} from "@/lib/catalog";

/**
 * Technology Detail(Phase 5C Finishing 追補v4)。
 *
 * 長文の百科事典にはしない: WHAT IS IT? / WHERE DOES IT FIT? /
 * WHEN DO YOU USE IT? / KEY CONCEPTS / COMMON COMPARISONS /
 * RELATED TECHNOLOGIESの短いセクション構成に絞る。API呼び出しは発生しない。
 *
 * 各セクションは(以前のような独立した白いCardの縦積みではなく)
 * `.tech-detail__section`のhairline区切りで、1本の読み物のように
 * 続けて読める構成にする(`app/globals.css`参照)。情報の順序・内容は
 * Phase 5Cから変更しない。
 */
export default function TechnologyDetailPage() {
  const params = useParams<{ id: string }>();
  const technology = getTechnology(params.id);

  if (!technology) {
    return (
      <PageContainer maxWidth={640}>
        <Alert
          tone="danger"
          title="Technologyが見つかりません"
          details="指定されたTechnologyは存在しません。"
        />
        <div style={{ marginTop: "var(--space-4)" }}>
          <Link href="/explore" style={{ color: "var(--color-accent)", fontWeight: 600 }}>
            ← Explore Technologiesに戻る
          </Link>
        </div>
      </PageContainer>
    );
  }

  const category = getCategory(technology.category);
  const commonComparisons = getCommonComparisons(technology.id);
  const relatedTechnologies = getRelatedTechnologies(technology.id);

  return (
    <PageContainer maxWidth={640}>
      {category && (
        <Link
          href={`/explore/${category.id}`}
          style={{
            display: "inline-block",
            fontSize: "0.85rem",
            fontWeight: 600,
            color: "var(--color-accent)",
            marginBottom: "var(--space-4)",
          }}
        >
          ← {category.name}
        </Link>
      )}

      <div style={{ marginBottom: "var(--space-5)" }}>
        <h1 className="report-header__title">{technology.name}</h1>
        <p style={{ color: "var(--color-text-muted)", marginTop: "var(--space-1)" }}>
          {technology.subcategory}
        </p>
      </div>

      <div className="tech-detail__section">
        <p className="evidence-detail__section-label">WHAT IS IT?</p>
        <p>{technology.whatItDoes}</p>
      </div>

      <div className="tech-detail__section">
        <p className="evidence-detail__section-label">WHERE DOES IT FIT?</p>
        <div className="where-it-fits">
          {technology.whereItFits.map((layer, index) => (
            <div key={layer} className="where-it-fits__layer">
              {index > 0 && <span className="where-it-fits__arrow">↓</span>}
              <span>{layer}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="tech-detail__section">
        <p className="evidence-detail__section-label">WHEN DO YOU USE IT?</p>
        <p>{technology.whenYouUseIt}</p>
      </div>

      <div className="tech-detail__section">
        <p className="evidence-detail__section-label">KEY CONCEPTS</p>
        <div className="concept-list">
          {technology.keyConceptIds.map((conceptId) => (
            <ConceptPopover key={conceptId} conceptId={conceptId} />
          ))}
        </div>
      </div>

      {commonComparisons.length > 0 && (
        <div className="tech-detail__section">
          <p className="evidence-detail__section-label">COMMON COMPARISONS</p>
          <div className="chip-group" role="group" aria-label="Common Comparisons">
            {commonComparisons.map((other) => (
              <Link
                key={other.id}
                href={`/compare/${technology.id}/${other.id}`}
                className="chip chip--link"
              >
                {other.name}
              </Link>
            ))}
          </div>
        </div>
      )}

      {relatedTechnologies.length > 0 && (
        <div className="tech-detail__section">
          <p className="evidence-detail__section-label">RELATED TECHNOLOGIES</p>
          <div className="chip-group" role="group" aria-label="Related Technologies">
            {relatedTechnologies.map((related) => (
              <Link
                key={related.id}
                href={`/explore/technology/${related.id}`}
                className="chip chip--link chip--muted"
              >
                {related.name}
              </Link>
            ))}
          </div>
        </div>
      )}
    </PageContainer>
  );
}
