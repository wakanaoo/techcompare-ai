/**
 * Technology Catalog(Phase 5C Prototype)。
 *
 * PostgreSQLに保存せず、frontendのstatic curated dataとして管理する
 * (Implementation Plan参照: API call不要・AI API cost 0・DB migration
 * 不要・catalog設計変更が容易であることを優先し、Prototype段階では
 * 過剰設計を避ける)。
 *
 * Server / Data / AIの3カテゴリ・10 technologiesのみを実装する
 * (Write/Interface/Run/Developは`data/categories.ts`でavailable: falseの
 * まま、Phase 5D以降で拡張する)。
 */

import type { CategoryId } from "./categories";

export interface Technology {
  id: string; // slug。URL(/explore/technology/[id]、/compare/[itemA]/[itemB])に使う
  /** 表示名。POST /research の item_a/item_b にもそのまま使う。 */
  name: string;
  category: CategoryId;
  subcategory: string;
  shortDescription: string;
  whatItDoes: string;
  whenYouUseIt: string;
  /** Technology Detailの「WHERE DOES IT FIT?」に表示する、上から下への層。 */
  whereItFits: string[];
  /** Concept.id への参照(Technology Detail内のpopoverで使う)。 */
  keyConceptIds: string[];
  /**
   * technology単位のBase Comparison Pointsのfallback。
   * 実際のCompare SetupではTechnologyRelation.comparisonCriteria
   * (ペア固有)を優先し、relationが無い場合だけこちらを使う
   * (lib/catalog.ts::getBaseComparisonCriteria()参照)。
   */
  baseComparisonCriteria: string[];
}

export const TECHNOLOGIES: Technology[] = [
  // --- SERVER ---
  {
    id: "fastapi",
    name: "FastAPI",
    category: "server",
    subcategory: "Python Web/API Framework",
    shortDescription: "型ヒントを活用して高速にAPIを構築できる、Python製のWebフレームワーク。",
    whatItDoes:
      "Pythonの型ヒントを使ってRequest/Responseの形を検証しながら、Web APIのEndpointを定義できるフレームワーク。非同期処理を標準でサポートしている。",
    whenYouUseIt: "AIアプリのBackendや、フロントエンドと分離したAPIサーバーを高速に作りたいとき。",
    whereItFits: ["Web / AI App", "Backend (FastAPI)"],
    keyConceptIds: ["framework", "api", "endpoint", "request", "response"],
    baseComparisonCriteria: ["Development speed", "Async support", "Type safety", "Ecosystem"],
  },
  {
    id: "django",
    name: "Django",
    category: "server",
    subcategory: "Python Web Framework",
    shortDescription:
      "管理画面・ORM・認証など主要機能が最初から揃った、Python製のフルスタックWebフレームワーク。",
    whatItDoes:
      "Webアプリに必要な機能(データベース操作・管理画面・認証・URLのRouting)を「規約」に沿って最初から提供するフレームワーク。",
    whenYouUseIt:
      "管理画面やユーザー認証を含む本格的なWebアプリを、機能をあまり自作せずに素早く立ち上げたいとき。",
    whereItFits: ["Web App", "Backend (Django)"],
    keyConceptIds: ["framework", "orm", "routing", "api"],
    baseComparisonCriteria: ["Built-in features", "Learning curve", "Development speed", "Ecosystem"],
  },
  {
    id: "flask",
    name: "Flask",
    category: "server",
    subcategory: "Python Web Framework",
    shortDescription: "必要な機能だけを組み合わせて使う、最小構成のPython製Webフレームワーク。",
    whatItDoes:
      "RoutingとRequest処理など最小限の機能だけを提供し、データベースやORM等は好きなライブラリを自分で組み合わせるフレームワーク。",
    whenYouUseIt: "小規模なAPIやプロトタイプを、余計な機能を持たずシンプルに作りたいとき。",
    whereItFits: ["Web App / Prototype", "Backend (Flask)"],
    keyConceptIds: ["framework", "routing", "endpoint", "api"],
    baseComparisonCriteria: ["Learning curve", "Flexibility", "Development speed"],
  },

  // --- DATA ---
  {
    id: "postgresql",
    name: "PostgreSQL",
    category: "data",
    subcategory: "Relational Database",
    shortDescription: "SQLを使って、表形式のデータを保存・検索・更新するためのデータベース。",
    whatItDoes:
      "データを行と列を持つTableに整理して保存し、SQLというQuery言語でデータを検索・更新・削除できるRelational Database。",
    whenYouUseIt: "ユーザー・商品・注文など、関係性のあるデータを厳密に保存したいとき。",
    whereItFits: ["Web / AI App", "Backend", "PostgreSQL"],
    keyConceptIds: ["database", "sql", "table", "schema", "relational-database"],
    baseComparisonCriteria: ["Feature richness", "Performance", "Operational simplicity"],
  },
  {
    id: "mysql",
    name: "MySQL",
    category: "data",
    subcategory: "Relational Database",
    shortDescription: "世界的に広く使われている、SQLベースのRelational Database。",
    whatItDoes:
      "PostgreSQLと同様にTable形式でデータを管理し、SQLでデータを操作するRelational Database。シンプルさと広い採用実績が特徴。",
    whenYouUseIt: "多くのホスティング環境・実績があるRelational Databaseを、標準的な選択肢として使いたいとき。",
    whereItFits: ["Web / AI App", "Backend", "MySQL"],
    keyConceptIds: ["database", "sql", "table", "relational-database"],
    baseComparisonCriteria: ["Ecosystem & hosting support", "Performance", "Operational simplicity"],
  },
  {
    id: "sqlite",
    name: "SQLite",
    category: "data",
    subcategory: "Embedded Relational Database",
    shortDescription: "サーバーを必要とせず、ファイル1つで動く軽量なRelational Database。",
    whatItDoes:
      "データベース全体を1つのファイルとして保存し、別プロセスのサーバーを立てずにアプリに組み込んで使えるRelational Database。",
    whenYouUseIt: "テスト用DB・小規模アプリ・ローカル環境など、サーバーを立てずに手軽にSQLを使いたいとき。",
    whereItFits: ["App", "SQLite (embedded)"],
    keyConceptIds: ["database", "sql", "table", "relational-database"],
    baseComparisonCriteria: ["Deployment simplicity", "Concurrent write support", "Scalability"],
  },
  {
    id: "mongodb",
    name: "MongoDB",
    category: "data",
    subcategory: "Document Database",
    shortDescription: "JSONに近い柔軟な構造のドキュメント単位でデータを保存するDocument Database。",
    whatItDoes:
      "あらかじめ固定のSchemaを決めずに、JSONのような形式のドキュメントをそのまま保存・検索できるDocument Database。",
    whenYouUseIt:
      "データの形式がアイテムごとに異なる・頻繁に変わる場合や、大量の書き込みを分散して扱いたいとき。",
    whereItFits: ["Web / AI App", "Backend", "MongoDB"],
    keyConceptIds: ["database", "document-database", "query", "schema"],
    baseComparisonCriteria: ["Schema flexibility", "Query capability", "Scalability"],
  },

  // --- AI ---
  {
    id: "gemini-api",
    name: "Gemini API",
    category: "ai",
    subcategory: "AI Model API",
    shortDescription: "Googleが提供するLLMを、APIを通じて自分のアプリに組み込めるサービス。",
    whatItDoes:
      "PromptをAPI経由でLLM(Model)に送り、生成された文章やStructured Outputを受け取れるサービス。Tool Callingにも対応。",
    whenYouUseIt: "自分のアプリに文章生成・要約・構造化データ抽出などのAI機能を組み込みたいとき。",
    whereItFits: ["App", "Gemini API", "LLM"],
    keyConceptIds: ["llm", "model", "prompt", "structured-output", "tool-calling"],
    baseComparisonCriteria: ["Pricing / free tier", "Structured output support", "Latency"],
  },
  {
    id: "openai-api",
    name: "OpenAI API",
    category: "ai",
    subcategory: "AI Model API",
    shortDescription: "OpenAIが提供するLLMを、APIを通じて自分のアプリに組み込めるサービス。",
    whatItDoes:
      "PromptをAPI経由でLLM(Model)に送り、生成された文章やStructured Outputを受け取れるサービス。Tool Callingにも対応。",
    whenYouUseIt: "自分のアプリに文章生成・要約・構造化データ抽出などのAI機能を組み込みたいとき。",
    whereItFits: ["App", "OpenAI API", "LLM"],
    keyConceptIds: ["llm", "prompt", "token", "structured-output"],
    baseComparisonCriteria: ["Pricing / free tier", "Structured output support", "Ecosystem & docs"],
  },
  {
    id: "claude-api",
    name: "Claude API",
    category: "ai",
    subcategory: "AI Model API",
    shortDescription: "Anthropicが提供するLLMを、APIを通じて自分のアプリに組み込めるサービス。",
    whatItDoes:
      "PromptをAPI経由でLLM(Model)に送り、生成された文章やStructured Outputを受け取れるサービス。長いContext WindowとTool Callingが特徴。",
    whenYouUseIt: "自分のアプリに文章生成・要約・構造化データ抽出などのAI機能を組み込みたいとき。",
    whereItFits: ["App", "Claude API", "LLM"],
    keyConceptIds: ["llm", "prompt", "context-window", "tool-calling"],
    baseComparisonCriteria: ["Reasoning quality", "Structured output support", "Ecosystem & docs"],
  },
];
