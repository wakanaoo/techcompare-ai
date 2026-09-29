"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Alert } from "@/components/Alert";
import { Card } from "@/components/Card";
import { PageContainer } from "@/components/PageContainer";
import { TechnologyCard } from "@/components/TechnologyCard";
import { getCategory, getTechnologiesByCategory } from "@/lib/catalog";

/**
 * Category(Phase 5C)。指定されたカテゴリに属するTechnology一覧を表示する。
 * API呼び出しは発生しない(static catalogの絞り込みのみ)。
 */
export default function CategoryPage() {
  const params = useParams<{ category: string }>();
  const category = getCategory(params.category);
  const technologies = category ? getTechnologiesByCategory(category.id) : [];

  if (!category) {
    return (
      <PageContainer maxWidth={880}>
        <Alert
          tone="danger"
          title="カテゴリが見つかりません"
          details="指定されたカテゴリは存在しません。"
        />
        <div style={{ marginTop: "var(--space-4)" }}>
          <Link href="/explore" style={{ color: "var(--color-accent)", fontWeight: 600 }}>
            ← Explore Technologiesに戻る
          </Link>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer maxWidth={880}>
      <Link
        href="/explore"
        style={{
          display: "inline-block",
          fontSize: "0.85rem",
          fontWeight: 600,
          color: "var(--color-accent)",
          marginBottom: "var(--space-4)",
        }}
      >
        ← Explore Technologies
      </Link>

      <div style={{ marginBottom: "var(--space-5)" }}>
        <p className="report-header__eyebrow">{category.domainLabel}</p>
        <h1 className="report-header__title">{category.name}</h1>
        <p style={{ color: "var(--color-text-muted)", marginTop: "var(--space-2)" }}>
          {category.question}
        </p>
      </div>

      {technologies.length === 0 ? (
        <Card>
          <p style={{ fontWeight: 700 }}>このカテゴリはまだ準備中です</p>
          <p style={{ color: "var(--color-text-muted)", marginTop: "var(--space-1)" }}>
            Phase 5C Prototypeでは、Server / Data / AIカテゴリのみ技術を掲載しています。
          </p>
        </Card>
      ) : (
        <div className="technology-grid">
          {technologies.map((technology) => (
            <TechnologyCard key={technology.id} technology={technology} />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
