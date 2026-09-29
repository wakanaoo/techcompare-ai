/**
 * Concept Dictionary(Phase 5C v1)。
 *
 * TechnologyとConceptは区別する: Technologyは実際に選択・導入して使う具体的
 * 技術やサービス、Conceptはそれを理解するための用語・考え方。独立した
 * Dictionaryページは作らず、Technology Detail内のpopover/expandable
 * (ConceptPopoverコンポーネント)でだけ表示する(ページ遷移で迷子にしない)。
 */

export interface Concept {
  id: string;
  name: string;
  /** popoverに表示する短い説明(1〜2文)。 */
  shortExplanation: string;
}

export const CONCEPTS: Concept[] = [
  // --- Web / Backend ---
  {
    id: "backend",
    name: "Backend",
    shortExplanation:
      "ユーザーの目に見えない裏側で、データの処理・保存・APIの提供を担う部分。",
  },
  {
    id: "framework",
    name: "Framework",
    shortExplanation:
      "アプリを作る際の土台となる、よく使う機能や決まりごとがあらかじめ用意されたソフトウェア。",
  },
  {
    id: "api",
    name: "API",
    shortExplanation: "プログラム同士がデータをやり取りするための、決まった約束事(窓口)。",
  },
  {
    id: "endpoint",
    name: "Endpoint",
    shortExplanation: "APIの中で、特定の機能・データにアクセスするための個別のURL。",
  },
  {
    id: "request",
    name: "Request",
    shortExplanation: "クライアントからサーバーへ送られる、処理を依頼する通信。",
  },
  {
    id: "response",
    name: "Response",
    shortExplanation: "サーバーがRequestを受け取って返す、処理結果の通信。",
  },
  {
    id: "routing",
    name: "Routing",
    shortExplanation: "URLごとに、どの処理を実行するかを振り分ける仕組み。",
  },

  // --- Data ---
  {
    id: "database",
    name: "Database",
    shortExplanation: "データを整理して保存し、後から検索・更新できるようにする仕組み。",
  },
  {
    id: "sql",
    name: "SQL",
    shortExplanation: "Relational Databaseに対して、データの検索・追加・更新を行うための言語。",
  },
  {
    id: "table",
    name: "Table",
    shortExplanation: "Relational Databaseで、行と列からなる表形式のデータのまとまり。",
  },
  {
    id: "schema",
    name: "Schema",
    shortExplanation: "データがどんな列・型・構造を持つかを定義したもの。",
  },
  {
    id: "query",
    name: "Query",
    shortExplanation: "データベースに対して「こういうデータが欲しい」と要求する命令。",
  },
  {
    id: "relational-database",
    name: "Relational Database",
    shortExplanation: "データを表形式で保存し、表同士を関連付けて扱うデータベース。",
  },
  {
    id: "document-database",
    name: "Document Database",
    shortExplanation: "JSONのような柔軟な構造のドキュメント単位でデータを保存するデータベース。",
  },
  {
    id: "orm",
    name: "ORM",
    shortExplanation:
      "SQLを直接書かずに、プログラムのコードからデータベースを操作できるようにする仕組み。",
  },

  // --- AI ---
  {
    id: "llm",
    name: "LLM",
    shortExplanation: "大量のテキストで学習され、文章の生成や理解ができるAIモデル。",
  },
  {
    id: "model",
    name: "Model",
    shortExplanation: "学習済みのAIそのもの。入力を受け取り、出力を生成する。",
  },
  {
    id: "prompt",
    name: "Prompt",
    shortExplanation: "LLMに与える入力の指示文。",
  },
  {
    id: "token",
    name: "Token",
    shortExplanation: "LLMが処理する際のテキストの最小単位。料金や上限もこの単位で数える。",
  },
  {
    id: "context-window",
    name: "Context Window",
    shortExplanation: "LLMが一度に読み込める入力と出力を合わせた最大の量。",
  },
  {
    id: "structured-output",
    name: "Structured Output",
    shortExplanation: "LLMの出力を自由な文章ではなく、決まった形式(JSON等)で受け取る仕組み。",
  },
  {
    id: "tool-calling",
    name: "Tool Calling",
    shortExplanation: "LLMが必要に応じて外部の関数やAPIを呼び出せるようにする仕組み。",
  },
];
