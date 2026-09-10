"""Phase 4 Evaluation Set: 固定15ケース。

各ケースは実際の POST /research と同じ入力(item_a, item_b, goal, criteria)。
以下の観点で多様性を持たせている:
  - criteria件数を1〜5(許容される全レンジ)にばらけさせる
  - 情報源が豊富な定番技術と、情報源が薄いと予想されるマイナー技術を混在させる
  - 明確に優劣がつきそうな組み合わせと、tie(引き分け)になりそうな組み合わせを混在させる

注意: 各ケースの組み合わせは「ケースの多様性を作るための設計意図」に過ぎず、
「どちらが勝つべきか」というground truth(正解ラベル)ではない。
技術選定はgoal/criteria次第で変わるため、期待winnerを設定してaccuracyを
計算することはしない(README Phase4セクション参照)。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    item_a: str
    item_b: str
    goal: str
    criteria: list[str] = field(default_factory=list)


EVALUATION_CASES: list[EvaluationCase] = [
    EvaluationCase(
        case_id="c01",
        item_a="FastAPI",
        item_b="Django",
        goal="個人開発のAI Webアプリのバックエンドとして採用したい",
        criteria=["development_speed"],
    ),
    EvaluationCase(
        case_id="c02",
        item_a="React",
        item_b="Vue",
        goal="社内向け管理画面のフロントエンドを新規に立ち上げたい",
        criteria=["learning_curve", "ecosystem"],
    ),
    EvaluationCase(
        case_id="c03",
        item_a="PostgreSQL",
        item_b="MySQL",
        goal="新規SaaSプロダクトのメインDBを選定したい",
        criteria=["performance", "operability", "ecosystem"],
    ),
    EvaluationCase(
        case_id="c04",
        item_a="Rust",
        item_b="Go",
        goal="高負荷なバックエンドAPIサーバーを新しい言語で書き直したい",
        criteria=["performance", "type_safety", "async_support"],
    ),
    EvaluationCase(
        case_id="c05",
        item_a="Kubernetes",
        item_b="Docker Swarm",
        goal="小規模チームでコンテナオーケストレーションを導入したい",
        criteria=["deployability", "operability"],
    ),
    EvaluationCase(
        case_id="c06",
        item_a="Next.js",
        item_b="Remix",
        goal="SEOを重視するWebメディアのフレームワークを選定したい",
        criteria=["development_speed", "ecosystem", "deployability", "learning_curve"],
    ),
    EvaluationCase(
        case_id="c07",
        item_a="GraphQL",
        item_b="REST",
        goal="複数クライアント(Web/モバイル)向けAPIの設計方針を決めたい",
        criteria=["development_speed", "ecosystem", "ai_compatibility"],
    ),
    EvaluationCase(
        case_id="c08",
        item_a="TypeScript",
        item_b="Flow",
        goal="既存の大規模JavaScriptプロジェクトに型システムを導入したい",
        criteria=["type_safety", "ecosystem"],
    ),
    EvaluationCase(
        case_id="c09",
        item_a="Terraform",
        item_b="Pulumi",
        goal="クラウドインフラをコードで管理する仕組みを整えたい",
        criteria=["learning_curve", "deployability", "ecosystem"],
    ),
    EvaluationCase(
        case_id="c10",
        item_a="Redis",
        item_b="Memcached",
        goal="Webアプリのセッション・キャッシュストアを選定したい",
        criteria=["performance", "operability"],
    ),
    EvaluationCase(
        case_id="c11",
        item_a="Svelte",
        item_b="SolidJS",
        goal="小規模だが長期的にメンテナンスするフロントエンドの技術を選びたい",
        criteria=[
            "learning_curve",
            "performance",
            "ecosystem",
            "development_speed",
            "type_safety",
        ],
    ),
    EvaluationCase(
        case_id="c12",
        item_a="AWS Lambda",
        item_b="Cloudflare Workers",
        goal="低コストで運用できるサーバーレスAPIの実行環境を選びたい",
        criteria=["cost", "deployability", "performance"],
    ),
    EvaluationCase(
        case_id="c13",
        item_a="Prisma",
        item_b="SQLAlchemy",
        goal="型安全性を重視してORMを選定したい",
        criteria=["type_safety", "ai_compatibility"],
    ),
    EvaluationCase(
        case_id="c14",
        item_a="gRPC",
        item_b="REST",
        goal="マイクロサービス間の内部通信プロトコルを選びたい",
        criteria=["performance"],
    ),
    EvaluationCase(
        case_id="c15",
        item_a="Zig",
        item_b="Rust",
        goal="組み込み・システムプログラミング向けの新しい言語を試したい",
        criteria=["performance", "learning_curve", "type_safety", "ecosystem"],
    ),
]


# LLM Judge対象として抽出する5ケース(層化抽出、設計意図はREADME参照):
#   c01: criteria最小(1件)
#   c11: criteria最大(5件) + マイナー技術で情報源が薄いと予想される
#   c07: 優劣が拮抗しやすい設計思想の比較(GraphQL vs REST)
#   c03: 情報源が豊富な定番技術同士の比較
#   c15: 最もマイナーな技術同士の比較(情報源が最も薄いと予想される)
JUDGE_SAMPLE_CASE_IDS: list[str] = ["c01", "c03", "c07", "c11", "c15"]


def get_case_by_id(case_id: str) -> EvaluationCase:
    for case in EVALUATION_CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(f"Unknown evaluation case_id: {case_id}")
