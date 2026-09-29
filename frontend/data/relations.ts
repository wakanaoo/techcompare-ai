/**
 * Technology間のrelation(Phase 5C Prototype)。
 *
 * relationとcomparison候補は混同しない: ALTERNATIVE / TRADE_OFFだけが
 * 「Common Comparisons」(比較する意味がある相手)として扱われる。
 * WORKS_WITH / BUILT_WITHはTechnology Detailの「Related Technologies」
 * (関連はあるが通常は代替比較の対象ではない技術)にのみ使う
 * (lib/catalog.ts::getCommonComparisons() / getRelatedTechnologies() 参照)。
 *
 * BUILT_WITHはtype定義のみ用意し、Prototypeではデータを空にしている
 * (Implementation Plan B節: FastAPI/Django/Flaskの基盤であるPythonが
 * Writeカテゴリ未実装のためcatalogに存在せず、意味のある表示ができない。
 * Writeカテゴリ実装時にPhase 5Dで本格実装する)。
 *
 * Related Technologiesはcatalog内に実在するTechnologyだけを対象にする
 * (Implementation Plan A節: SQLAlchemy/pgvector等、まだcatalogに無い
 * 技術へのリンクは作らない)。
 */

export type RelationType = "ALTERNATIVE" | "TRADE_OFF" | "BUILT_WITH" | "WORKS_WITH";

export interface TechnologyRelation {
  /** Technology.id。無向対として扱う(a/bの順序に意味はない)。 */
  a: string;
  b: string;
  type: RelationType;
  /**
   * Compare Setupの「How are they related?」に表示する説明。
   * ALTERNATIVE/TRADE_OFF(Common Comparisons)のみ必須。
   */
  relationSummary?: string;
  /**
   * このペア固有のBase Comparison Points。
   * ALTERNATIVE/TRADE_OFF(Common Comparisons)のみ必須。
   */
  comparisonCriteria?: string[];
}

export const TECHNOLOGY_RELATIONS: TechnologyRelation[] = [
  // --- Comparison Relations v1 (ALTERNATIVE / TRADE_OFF) ---
  {
    a: "fastapi",
    b: "django",
    type: "ALTERNATIVE",
    relationSummary:
      "どちらもPythonのWebフレームワークですが、FastAPIは型ヒントを活かした軽量なAPI構築に強く、Djangoは管理画面・ORM・認証など「最初から揃っている」フルスタックな機能に強みがあります。",
    comparisonCriteria: ["Development speed", "Learning curve", "Built-in admin & auth", "API-first design"],
  },
  {
    a: "fastapi",
    b: "flask",
    type: "ALTERNATIVE",
    relationSummary:
      "どちらも軽量なPythonフレームワークですが、FastAPIは型ヒントと非同期処理を前提にした設計で、Flaskはより最小構成でシンプルに始められます。",
    comparisonCriteria: ["Learning curve", "Async support", "Type safety", "Ecosystem maturity"],
  },
  {
    a: "django",
    b: "flask",
    type: "ALTERNATIVE",
    relationSummary:
      "どちらもPythonの代表的なWebフレームワークですが、Djangoは規約と機能が最初から揃った「フルスタック」型、Flaskは必要な機能だけを組み合わせる「軽量」型です。",
    comparisonCriteria: ["Built-in features", "Flexibility", "Learning curve", "Project scale fit"],
  },
  {
    a: "postgresql",
    b: "mysql",
    type: "ALTERNATIVE",
    relationSummary:
      "どちらも代表的なRelational Databaseで、多くの機能が共通していますが、PostgreSQLは高度な機能・拡張性、MySQLはシンプルさと広い採用実績に強みがあります。",
    comparisonCriteria: ["Feature richness", "Performance", "Ecosystem & hosting support", "Operational simplicity"],
  },
  {
    a: "postgresql",
    b: "mongodb",
    type: "TRADE_OFF",
    relationSummary:
      "どちらもアプリのデータ保存に使われますが、PostgreSQLは表形式でデータの関係性を厳密に扱い、MongoDBはJSONに近い柔軟な構造でデータを保存します。",
    comparisonCriteria: ["Query capability", "Schema flexibility", "Operations"],
  },
  {
    a: "postgresql",
    b: "sqlite",
    type: "TRADE_OFF",
    relationSummary:
      "同じSQLベースのデータベースですが、PostgreSQLは独立したサーバーとして動く本格運用向け、SQLiteはファイル1つで動く組み込み向けです。",
    comparisonCriteria: ["Deployment simplicity", "Concurrent write support", "Scalability"],
  },
  {
    a: "mysql",
    b: "sqlite",
    type: "TRADE_OFF",
    relationSummary:
      "同じSQLベースのデータベースですが、MySQLはサーバーとして動く本格運用向け、SQLiteはファイル1つで動く組み込み向けです。",
    comparisonCriteria: ["Deployment simplicity", "Concurrent write support", "Scalability"],
  },
  {
    a: "gemini-api",
    b: "openai-api",
    type: "ALTERNATIVE",
    relationSummary:
      "どちらも汎用的なLLMをAPI経由で利用できるサービスですが、提供元・料金体系・Structured OutputやTool Callingの実装方法が異なります。",
    comparisonCriteria: ["Pricing / free tier", "Structured output support", "Latency", "Ecosystem & docs"],
  },
  {
    a: "gemini-api",
    b: "claude-api",
    type: "ALTERNATIVE",
    relationSummary:
      "どちらも汎用的なLLMをAPI経由で利用できるサービスですが、提供元・料金体系・Structured OutputやTool Callingの実装方法が異なります。",
    comparisonCriteria: ["Pricing / free tier", "Structured output support", "Reasoning quality", "Ecosystem & docs"],
  },
  {
    a: "openai-api",
    b: "claude-api",
    type: "ALTERNATIVE",
    relationSummary:
      "どちらも汎用的なLLMをAPI経由で利用できるサービスですが、提供元・料金体系・Structured OutputやTool Callingの実装方法が異なります。",
    comparisonCriteria: ["Pricing / free tier", "Structured output support", "Reasoning quality", "Ecosystem & docs"],
  },

  // --- WORKS_WITH(catalog内技術同士のみ、Related Technologies用) ---
  { a: "fastapi", b: "postgresql", type: "WORKS_WITH" },
  { a: "fastapi", b: "mongodb", type: "WORKS_WITH" },
  { a: "django", b: "postgresql", type: "WORKS_WITH" },
  { a: "flask", b: "sqlite", type: "WORKS_WITH" },
  { a: "fastapi", b: "gemini-api", type: "WORKS_WITH" },

  // --- BUILT_WITH: Prototypeではデータ無し(上記コメント参照) ---
];
