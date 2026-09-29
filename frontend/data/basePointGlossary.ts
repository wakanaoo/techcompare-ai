/**
 * Compare SetupのBase Points(catalog由来、`data/relations.ts`の
 * `comparisonCriteria`と`data/technologies.ts`の`baseComparisonCriteria`に
 * 登場する英語の自然文フレーズ)向けの、短い日本語説明の辞書(Phase 5C
 * Finishing)。
 *
 * `lib/criteria.ts::CRITERION_OPTIONS`の10候補(Learning curve等)と重複する
 * フレーズはここには含めない(そちらのdescriptionをそのまま使う。
 * `lib/catalog.ts::getBasePointDescription()`参照)。
 *
 * ここに無いフレーズ(AI提案・custom入力)はtooltip自体を表示しない
 * (説明を無理に生成しない)。
 */
export const BASE_POINT_GLOSSARY: Record<string, string> = {
  "Built-in admin & auth": "管理画面や認証機能が最初から用意されているか。",
  "API-first design": "画面(UI)を持たず、APIとしての設計・利用のしやすさを優先しているか。",
  "Ecosystem maturity": "ライブラリ・情報・実績がどれだけ成熟しているか。",
  "Built-in features": "最初から用意されている標準機能の豊富さ。",
  Flexibility: "構成やライブラリの組み合わせを自由に選べる度合い。",
  "Project scale fit": "プロジェクトの規模(小規模〜大規模)にどれだけ合っているか。",
  "Feature richness": "備えている機能の豊富さ・高度さ。",
  "Ecosystem & hosting support": "ホスティング環境や周辺ツールの対応・充実度。",
  "Operational simplicity": "日々の運用(監視・保守・チューニング)のシンプルさ。",
  "Query capability": "データの検索・集計をどれだけ柔軟に行えるか。",
  "Schema flexibility": "データの形式(スキーマ)をどれだけ柔軟に変更できるか。",
  Operations: "バックアップ・監視・スケーリングなど、運用のしやすさ全般。",
  "Deployment simplicity": "本番環境への配置・セットアップのシンプルさ。",
  "Concurrent write support": "複数の書き込みが同時に発生する状況への強さ。",
  Scalability: "データ量やアクセス増加に応じて拡張できるか。",
  "Pricing / free tier": "料金体系や無料枠の使いやすさ。",
  "Structured output support": "決まった形式(JSON等)でのデータ出力への対応。",
  Latency: "応答が返ってくるまでの速さ。",
  "Ecosystem & docs": "ライブラリ・ドキュメント・コミュニティ情報の充実度。",
  "Reasoning quality": "複雑な指示や推論をどれだけ正確にこなせるか。",
};
