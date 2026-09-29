import { CategoryCard } from "@/components/CategoryCard";
import { PageContainer } from "@/components/PageContainer";
import { CATEGORIES } from "@/data/categories";
import { getTechnologiesByCategory } from "@/lib/catalog";

/**
 * Technology Map(Phase 5C)。
 *
 * 静的catalogデータの一覧表示のみで、API呼び出しは発生しない
 * (Implementation Plan: Technology Map閲覧はAPI call 0)。
 */
export default function ExplorePage() {
  return (
    <PageContainer maxWidth={880}>
      <div style={{ marginBottom: "var(--space-5)" }}>
        <h1>Explore Technologies</h1>
      </div>

      <div className="category-grid">
        {CATEGORIES.map((category) => (
          <CategoryCard
            key={category.id}
            category={category}
            technologyCount={getTechnologiesByCategory(category.id).length}
          />
        ))}
      </div>
    </PageContainer>
  );
}
