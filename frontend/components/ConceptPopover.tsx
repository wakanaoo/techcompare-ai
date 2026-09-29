"use client";

import { getConcept } from "@/lib/catalog";
import { InfoTooltip } from "./InfoTooltip";

interface ConceptPopoverProps {
  conceptId: string;
}

/**
 * Technology Detail内でConceptの名前にhover/focus/tapすると、短い説明が
 * その場に浮かぶ(Phase 5C Finishingから、Base Pointsと同じ`InfoTooltip`に
 * 統一。以前の「クリックでinline展開/折りたたみ」方式は廃止した)。
 *
 * TechnologyとConceptは区別する(Concept Dictionaryは独立ページを持たない)。
 * ページ遷移せずインラインで完結させることで、初心者が画面を渡り歩いて
 * 迷子になる構造を避ける。
 */
export function ConceptPopover({ conceptId }: ConceptPopoverProps) {
  const concept = getConcept(conceptId);

  if (!concept) return null;

  return (
    <InfoTooltip
      className="concept-popover"
      triggerLabel={`${concept.name}の説明`}
      description={concept.shortExplanation}
    >
      {concept.name}
    </InfoTooltip>
  );
}
