import Link from "next/link";

import type { Technology } from "@/data/technologies";
import { Card } from "./Card";

interface TechnologyCardProps {
  technology: Technology;
}

/**
 * Category一覧に並べる、1 Technology分の軽量カード(Phase 5C Finishing 追補v4)。
 *
 * 技術名・種類を主役にし、`shortDescription`はhover/keyboard focus時だけ
 * ふわっと現れるsecondary informationとして扱う(`.technology-card__description-wrap`、
 * `app/globals.css`参照。hoverが無い端末では常時表示にfallbackする)。
 */
export function TechnologyCard({ technology }: TechnologyCardProps) {
  return (
    <Link href={`/explore/technology/${technology.id}`} className="technology-card__link">
      <Card className="technology-card">
        <p className="technology-card__name">{technology.name}</p>
        <p className="technology-card__subcategory">{technology.subcategory}</p>
        <div className="technology-card__description-wrap">
          <p className="technology-card__description">{technology.shortDescription}</p>
        </div>
      </Card>
    </Link>
  );
}
