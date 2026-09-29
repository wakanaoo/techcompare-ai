/**
 * Direct Compare(Home)のTechnology A/B向け、curatedなpair example(追補v3)。
 * API/Gemini/Tavilyは使わない静的data。
 *
 * "goalの文章例"(`data/useCaseExamples.ts`)とは別概念(こちらはTechnology
 * A/Bそのものの組み合わせ)なので、別ファイルに分けている。
 *
 * 現時点ではExplore/Technology Map(`data/technologies.ts`)に実装済みの
 * 技術の組み合わせだけを載せる(Homeのexampleから、Interfaceのようなまだ
 * 実装していないカテゴリへ誘導しないため)。Interfaceカテゴリ実装後、
 * React/Vue等を追加する余地は残している。
 */

export interface TechnologyPairExample {
  itemA: string;
  itemB: string;
}

export const TECHNOLOGY_PAIR_EXAMPLES: TechnologyPairExample[] = [
  { itemA: "FastAPI", itemB: "Django" },
  { itemA: "PostgreSQL", itemB: "MongoDB" },
  { itemA: "PostgreSQL", itemB: "MySQL" },
  { itemA: "Gemini API", itemB: "OpenAI API" },
  { itemA: "OpenAI API", itemB: "Claude API" },
];
