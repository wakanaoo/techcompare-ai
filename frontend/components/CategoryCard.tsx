import Link from "next/link";

import type { Category } from "@/data/categories";
import { Badge } from "./Badge";
import { Card } from "./Card";

interface CategoryCardProps {
  category: Category;
  technologyCount: number;
}

/**
 * Technology Mapの1カテゴリ分のカード(Phase 5C Finishing 追補v4)。
 *
 * 通常状態ではname/domain/badgeだけを見せ、`question`(補足説明)は
 * `.category-card__question-wrap`によりhover/keyboard focus時だけ
 * ふわっと現れるsecondary informationとして扱う(`app/globals.css`参照。
 * hoverが無い端末では常時表示にfallbackする)。
 *
 * `category.available === false`(Phase 5C Prototypeで未実装のカテゴリ)は
 * リンクにせず「Coming soon」表示にする(progressive disclosure。大量の
 * カードを同じ密度で並べず、今使えるものだけを目立たせる)。
 */
export function CategoryCard({ category, technologyCount }: CategoryCardProps) {
  const content = (
    <Card className={category.available ? "category-card" : "category-card category-card--disabled"}>
      <div className="category-card__header">
        <span className="category-card__name">{category.name}</span>
        {category.available ? (
          <Badge tone="info">{technologyCount} technologies</Badge>
        ) : (
          <Badge tone="neutral">Coming soon</Badge>
        )}
      </div>
      <p className="category-card__domain">{category.domainLabel}</p>
      <div className="category-card__question-wrap">
        <p className="category-card__question">{category.question}</p>
      </div>
    </Card>
  );

  if (!category.available) {
    return content;
  }

  return (
    <Link href={`/explore/${category.id}`} className="category-card__link">
      {content}
    </Link>
  );
}
