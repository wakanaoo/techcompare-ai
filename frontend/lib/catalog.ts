/**
 * Technology Catalog(static curated data)のlookupヘルパー。
 *
 * data/*.ts の配列を素朴に検索する純粋関数のみで構成する(API呼び出し・
 * 副作用なし)。Explore系ページ・Compare Setupはこれらの関数経由でのみ
 * catalogデータへアクセスする。
 */

import { BASE_POINT_GLOSSARY } from "@/data/basePointGlossary";
import { CATEGORIES, type Category } from "@/data/categories";
import { CONCEPTS, type Concept } from "@/data/concepts";
import { TECHNOLOGIES, type Technology } from "@/data/technologies";
import {
  TECHNOLOGY_RELATIONS,
  type RelationType,
  type TechnologyRelation,
} from "@/data/relations";
import {
  GENERIC_USE_CASE_EXAMPLES,
  PAIR_USE_CASE_EXAMPLES,
  pairExampleKey,
} from "@/data/useCaseExamples";
import { CRITERION_OPTIONS, canonicalCriterionKey } from "@/lib/criteria";

// idの型はstring(URLのdynamic route paramsは常にstringのため、呼び出し側で
// castせずそのまま渡せるようにする)。存在しないidはundefinedを返すだけで、
// 例外は投げない。

export function getCategory(id: string): Category | undefined {
  return CATEGORIES.find((c) => c.id === id);
}

export function getTechnology(id: string): Technology | undefined {
  return TECHNOLOGIES.find((t) => t.id === id);
}

export function getTechnologiesByCategory(categoryId: string): Technology[] {
  return TECHNOLOGIES.filter((t) => t.category === categoryId);
}

export function getConcept(id: string): Concept | undefined {
  return CONCEPTS.find((c) => c.id === id);
}

/** 2つのTechnology間のrelationを、a/bどちらの順序でも見つける(対称lookup)。 */
export function getRelation(idA: string, idB: string): TechnologyRelation | undefined {
  return TECHNOLOGY_RELATIONS.find(
    (r) => (r.a === idA && r.b === idB) || (r.a === idB && r.b === idA),
  );
}

function relationsFor(id: string, type: RelationType): TechnologyRelation[] {
  return TECHNOLOGY_RELATIONS.filter(
    (r) => r.type === type && (r.a === id || r.b === id),
  );
}

function otherSide(relation: TechnologyRelation, id: string): string {
  return relation.a === id ? relation.b : relation.a;
}

/**
 * Common Comparisons(比較する意味がある相手)。ALTERNATIVE/TRADE_OFFのみを
 * 対象にする(WORKS_WITH/BUILT_WITHはrelationがあってもcomparison候補では
 * ないため、ここには含めない)。
 */
export function getCommonComparisons(id: string): Technology[] {
  const alternatives = relationsFor(id, "ALTERNATIVE");
  const tradeOffs = relationsFor(id, "TRADE_OFF");

  return [...alternatives, ...tradeOffs]
    .map((r) => getTechnology(otherSide(r, id)))
    .filter((t): t is Technology => t !== undefined);
}

/**
 * Related Technologies(関連はあるが通常は代替比較の対象ではない技術)。
 * WORKS_WITH/BUILT_WITHのみを対象にする。catalogに存在するTechnologyだけを
 * relationデータとして持たせているため、ここで返す技術は常にクリック可能な
 * Technology Detailを持つ(Implementation Plan A節)。
 */
export function getRelatedTechnologies(id: string): Technology[] {
  const worksWith = relationsFor(id, "WORKS_WITH");
  const builtWith = relationsFor(id, "BUILT_WITH");

  return [...worksWith, ...builtWith]
    .map((r) => getTechnology(otherSide(r, id)))
    .filter((t): t is Technology => t !== undefined);
}

/**
 * Compare SetupのBase Comparison Pointsを決定する。
 * relation固有のcomparisonCriteriaがあればそれを優先し、無ければ両方の
 * Technology.baseComparisonCriteriaを合わせて重複を除いたものを使う
 * (Common Comparisons経由なら常にrelationが存在するため、fallbackは
 * 主に将来の直接URL指定・データ欠落時の安全策)。
 */
export function getBaseComparisonCriteria(idA: string, idB: string): string[] {
  const relation = getRelation(idA, idB);
  if (relation?.comparisonCriteria) {
    return relation.comparisonCriteria;
  }

  const techA = getTechnology(idA);
  const techB = getTechnology(idB);
  const merged = [
    ...(techA?.baseComparisonCriteria ?? []),
    ...(techB?.baseComparisonCriteria ?? []),
  ];

  const seen = new Set<string>();
  const deduped: string[] = [];
  for (const point of merged) {
    const key = canonicalCriterionKey(point);
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(point);
  }
  return deduped;
}

/**
 * Base Point(固定候補・Compare SetupのBase Points双方)の短い日本語説明を
 * 探す(InfoTooltip表示用)。`lib/criteria.ts::CRITERION_OPTIONS`の10候補を
 * 優先し、無ければcatalog由来フレーズの辞書(`data/basePointGlossary.ts`)を見る。
 * どちらにも無い場合(AI提案・custom入力)はundefinedを返し、tooltip自体を
 * 表示しない(説明を無理に生成しない)。
 */
export function getBasePointDescription(label: string): string | undefined {
  const lowered = label.trim().toLowerCase();

  const generic = CRITERION_OPTIONS.find((option) => option.label.toLowerCase() === lowered);
  if (generic) return generic.description;

  const glossaryKey = Object.keys(BASE_POINT_GLOSSARY).find(
    (key) => key.toLowerCase() === lowered,
  );
  return glossaryKey ? BASE_POINT_GLOSSARY[glossaryKey] : undefined;
}

/** Technology.nameから(大文字小文字を無視して)idを逆引きする(Direct Compareの自由入力用)。 */
export function findTechnologyIdByName(name: string): string | undefined {
  const trimmed = name.trim().toLowerCase();
  if (!trimmed) return undefined;
  return TECHNOLOGIES.find((t) => t.name.toLowerCase() === trimmed)?.id;
}

/**
 * "What are you building?"のUse Case Examplesを返す(静的データのみ、
 * API呼び出しなし)。両方のidがcatalogのTechnologyとして解決でき、かつ
 * そのペア固有のcurated examplesがあればそれを、無ければ技術非依存の
 * 汎用exampleへfallbackする。
 */
export function getUseCaseExamples(idA?: string, idB?: string): string[] {
  if (idA && idB) {
    const pairExamples = PAIR_USE_CASE_EXAMPLES[pairExampleKey(idA, idB)];
    if (pairExamples) return pairExamples;
  }
  return GENERIC_USE_CASE_EXAMPLES;
}
