/**
 * "What are you building?"欄向けの、静的でcuratedなUse Case Examples
 * (Phase 5C Finishing)。API/Gemini/Tavilyは一切使わない。
 *
 * `PAIR_USE_CASE_EXAMPLES`はTechnology pair(catalogのid 2つ)ごとの例文で、
 * `data/relations.ts`のComparison Relations(ALTERNATIVE/TRADE_OFF)と
 * 同じ9ペアをカバーする。keyは2つのidをアルファベット順にsortして
 * "|"で結合したもの(`getRelation()`と同じ対称lookupを、配列探索ではなく
 * O(1)のRecord lookupで行うための正規化)。
 *
 * Direct Compare(Home)はTechnology A/Bが自由入力でcatalogに存在しない
 * ことが多いため、その場合は`GENERIC_USE_CASE_EXAMPLES`(技術非依存)へ
 * fallbackする(`lib/catalog.ts::getUseCaseExamples()`参照)。
 */

export function pairExampleKey(idA: string, idB: string): string {
  return [idA, idB].sort().join("|");
}

export const PAIR_USE_CASE_EXAMPLES: Record<string, string[]> = {
  [pairExampleKey("fastapi", "django")]: [
    "個人開発でAIアプリのバックエンドAPIを素早く作りたい",
    "管理画面や認証を含む本格的なWebアプリを立ち上げたい",
    "スタートアップの新規プロダクトを少人数で開発したい",
  ],
  [pairExampleKey("fastapi", "flask")]: [
    "小規模なAPIをシンプルな構成で試作したい",
    "型ヒントを活かして安全にAPIを書きたい",
    "非同期処理が多いWebサービスを作りたい",
  ],
  [pairExampleKey("django", "flask")]: [
    "管理画面付きの業務システムを素早く立ち上げたい",
    "必要な機能だけを組み合わせた軽量なアプリにしたい",
    "チームの規模に合ったフレームワークを選びたい",
  ],
  [pairExampleKey("postgresql", "mysql")]: [
    "複雑な検索条件を扱うECサイトのデータベースを選びたい",
    "多くのホスティングサービスで実績のあるDBを使いたい",
    "将来的な機能拡張を見据えて高機能なDBにしたい",
  ],
  [pairExampleKey("postgresql", "mongodb")]: [
    "プロトタイプのSNSアプリで投稿を大量保存したい",
    "ユーザーや注文など関係性の厳密なデータを扱いたい",
    "データの形式が頻繁に変わるアプリを作りたい",
  ],
  [pairExampleKey("postgresql", "sqlite")]: [
    "サーバーを立てずに手軽に試作したい",
    "本番運用を見据えた堅牢なDBにしたい",
    "テスト環境を軽量に構築したい",
  ],
  [pairExampleKey("mysql", "sqlite")]: [
    "サーバーを立てずに手軽に試作したい",
    "多くの実績があるDBで本番運用したい",
    "ローカル環境だけで完結するアプリを作りたい",
  ],
  [pairExampleKey("gemini-api", "openai-api")]: [
    "無料枠を使ってAI機能を試作したい",
    "構造化データの抽出を安定して行いたい",
    "レイテンシの低いAI応答を実現したい",
  ],
  [pairExampleKey("gemini-api", "claude-api")]: [
    "無料枠を使ってAI機能を試作したい",
    "複雑な推論を伴うタスクを任せたい",
    "構造化データの抽出を安定して行いたい",
  ],
  [pairExampleKey("openai-api", "claude-api")]: [
    "複雑な推論を伴うタスクを任せたい",
    "構造化データの抽出を安定して行いたい",
    "ドキュメントやエコシステムが充実したAPIを使いたい",
  ],
};

export const GENERIC_USE_CASE_EXAMPLES: string[] = [
  "個人開発の小規模サービスで使いたい",
  "プロトタイプを素早く検証したい",
  "本番運用を見据えて長期的に使いたい",
  "チームでの開発生産性を重視したい",
];
