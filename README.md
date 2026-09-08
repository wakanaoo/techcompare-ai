# TechCompare AI

技術選定(例: FastAPI vs Django)を、複数の情報源の調査・構造化・比較・根拠提示によって
サポートするResearch & Comparison Toolです。AI/Web開発の学習ツールも兼ねています。

**現在のフェーズ: Phase 2 (LLMによる構造化比較)**

New Research画面 → `POST /research` → PostgreSQLへ保存 → LLM(Gemini API)へ
比較依頼 → Structured Outputで比較結果取得 → PostgreSQLへ保存 →
Comparison Report画面で表示、という流れが動く状態です。

> **重要**: Phase 2の比較結果はLLM自身の知識のみに基づいて生成されており、
> Web検索等の外部情報源によってGroundingされていません。**最終仕様ではありません。**
> Phase 3以降でSearch API・信頼できるSource・Evidence・Citationを追加し、
> 根拠を確認できるようにする予定です。

## 技術構成

| レイヤー | 技術 |
|---|---|
| Frontend | Next.js (App Router) / React / TypeScript |
| Backend | Python / FastAPI / Pydantic / SQLAlchemy / Alembic |
| Database | PostgreSQL (Docker Compose) |
| AI | Google Gemini API (`gemini-3.6-flash`, Structured Output) |
| Testing | pytest (LLM呼び出しはmock) |

## ディレクトリ構成

```
.
├── docker-compose.yml   # PostgreSQLコンテナのみ定義
├── .env.example         # docker-compose用の環境変数サンプル
├── backend/              # FastAPI
│   ├── alembic/               # DB migration
│   ├── app/
│   │   ├── main.py               # アプリのエントリーポイント
│   │   ├── api/research.py       # POST/GET /research, GET /research/{id}/result
│   │   ├── models/               # research.py, comparison.py (SQLAlchemy)
│   │   ├── schemas/              # research.py, criteria.py (Pydantic, API用)
│   │   ├── services/
│   │   │   ├── llm_schemas.py       # LLM Structured Output用スキーマ
│   │   │   ├── llm_client.py        # Gemini API呼び出し
│   │   │   └── research_runner.py   # BackgroundTasksから呼ばれる処理本体
│   │   ├── db/session.py         # DB接続設定
│   │   └── core/config.py        # 環境変数の読み込み
│   ├── tests/
│   └── .env.example
└── frontend/             # Next.js
    ├── app/page.tsx                          # New Research画面
    ├── app/research/[id]/page.tsx            # Research Progress画面(polling)
    ├── app/research/[id]/result/page.tsx     # Comparison Report画面
    ├── lib/api.ts                            # Backend呼び出し用クライアント
    ├── lib/criteria.ts                       # 比較軸の固定候補
    └── .env.local.example
```

## セットアップ手順

### 1. PostgreSQLを起動する(Docker)

```bash
cp .env.example .env   # 値は好きに変更してよい(devなのでコミットはされない)
docker compose up -d db
```

### 2. Backend (FastAPI) を起動する

```bash
cd backend
cp .env.example .env   # DATABASE_URLは上のPostgreSQL設定と揃える。GEMINI_API_KEYも設定する
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head     # DBスキーマを最新化する(初回・Phase 2以降は毎回)
uvicorn app.main:app --reload
```

`http://localhost:8000/health` が `{"status": "ok"}` を返せば起動成功です。

### 3. Frontend (Next.js) を起動する

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

`http://localhost:3000` を開き、New Research画面から技術2つ・目的・比較軸を入力すると、
Research Progress画面で進捗がpollingされ、完了するとComparison Report画面に自動遷移します。

### LLM APIキーの設定

`backend/.env` の `GEMINI_API_KEY` に、Google AI StudioのAPI Keysページ
(https://aistudio.google.com/apikey) で発行したキーを設定してください。
クレジットカード登録は不要です。キーは`.env`にのみ置き、コード・ログ・commitには
含めません。

キーが未設定/無効な場合、Researchのstatusは自動的に`failed`になり、
`error_message`にエラー内容が保存されます(サーバー自体はクラッシュしません)。

## テスト

```bash
cd backend
source venv/bin/activate
pytest -v
```

BackendのテストはPostgreSQLやGEMINI_API_KEYがなくても実行できます。
DBはテスト専用のSQLiteファイルに一時的に差し替え、LLM呼び出し
(`app.services.research_runner.generate_comparison`)は`monkeypatch`でmockに
差し替えているため、テストのたびに課金・ネットワーク通信は発生しません。
実際のLLM APIを使った確認は手動E2Eとして行います。

## Database Migration (Alembic)

Phase 2からAlembicを導入しました。

```bash
cd backend
source venv/bin/activate
alembic upgrade head          # 最新スキーマまで適用
alembic downgrade -1          # 直前のmigrationまで戻す
alembic revision --autogenerate -m "説明"   # モデル変更からmigrationを生成(要レビュー)
```

- `alembic/versions/de7d53756ae3_*.py` : 初期migration(Phase 1の`researches`テーブル)
- `alembic/versions/2d1d4f1c1aa2_*.py` : Phase 2 migration(`comparisons`テーブル追加、
  `researches`への列追加)

destructiveな変更(列やテーブルのDROPを伴うもの)はPhase 2時点では行っていません。

## API一覧 (Phase 2時点)

| Method | Path | 説明 |
|---|---|---|
| POST | `/research` | 新しいResearchを作成し、裏でLLM比較処理を開始する |
| GET | `/research/{id}` | Researchのstatus等を取得する(polling用の軽量API) |
| GET | `/research/{id}/result` | 完了したResearchの比較結果を取得する(未完了時は409、失敗時は422) |
| GET | `/health` | 死活監視用 |

## Database構造 (Phase 2時点)

```
researches
  id, item_a, item_b, goal,
  criteria (JSONB、比較軸のkeyの配列),
  status (pending/researching/completed/failed),
  recommendation_winner, recommendation_summary, recommendation_reason,
  error_message,
  created_at, updated_at

comparisons                          -- Research 1 : N Comparisons
  id, research_id (FK -> researches.id, ON DELETE CASCADE),
  criterion, criterion_label,
  item_a_summary, item_b_summary,
  item_a_score, item_b_score (1〜5, CHECK制約),
  winner (item_a/item_b/tie, CHECK制約),
  created_at
```

## LLM Provider選定

**Google Gemini API**を採用しています(`google-genai` SDK、`response_schema`による
Structured Output)。

最初はAnthropic Claude API(`claude-sonnet-5`)を選定していましたが、
「できるだけAPIコストをかけず、可能なら無料枠だけでMVPを完成させたい」という
制約を踏まえて再検討し、Gemini APIに切り替えました。

| 観点 | Anthropic Claude API | Google Gemini API |
|---|---|---|
| 無料枠 | なし(新規アカウントに$5・一度きりのトライアルクレジットのみ) | あり・継続的(クレジットカード登録不要、レート制限のみ) |
| Structured Output | `messages.parse(output_format=PydanticModel)`で直接的 | `response_schema`にPydanticモデルを渡す方式。ネストしたモデルでSDK側の既知の問題報告あり(要検証、後述のPoC参照) |
| Phase 3のWeb Search/Grounding | `web_search`ツールはあるが無料枠なし・最初の1回から課金 | モデル・時期によりFree Tierでの利用可否が変わる(下記の注意参照) |
| ポートフォリオとしての妥当性 | Structured Output実装が最も簡潔 | コスト制約下でのprovider再選定という技術判断自体も語れる材料になる |

Provider抽象化レイヤーは作らず、`app/services/llm_client.py`で直接呼び出しています
(MVPでは1 providerで十分なため)。

> **Phase 3のGrounding課金について(要再確認)**: 調査時点ではGemini 2.5系モデルの
> Free TierでGoogle Search Groundingが一定件数(日500件、Flash/Flash-Liteで共有)まで
> 無料という情報を確認していましたが、`gemini-2.5-flash`自体が新規ユーザー向けには
> 提供終了していたように、モデルラインナップ・料金条件は速いペースで変わります。
> 現在採用している`gemini-3.6-flash`を含む3.x系Flashは、調査時点ではFree Tierでの
> Grounding利用が非対応でした。**この情報は現時点では確定情報として扱いません**。
> Phase 3でGroundingの実装に着手する際は、必ず
> [Gemini API公式料金ページ](https://ai.google.dev/gemini-api/docs/pricing)で
> 対象モデル・最新の条件を再確認してください。

### LLMモデルの選定(`gemini-3.6-flash`)

公式ドキュメント調査の時点では、Flash系の中でも安定版(GA)かつ軽量な
`gemini-2.5-flash`がMVPの用途に必要十分と判断していました。

| 観点 | 判断(調査時点) |
|---|---|
| 安定版かどうか | Preview版ではなくGA(安定版) |
| Structured Output対応 | 提供中の全モデル共通機能として対応 |
| レイテンシ/コスト | 公式に「低レイテンシー・高量タスク向けベストプライス性能」と明記 |
| 無料枠 | あり |

しかし、本実装に着手する前のPoC(下記)で実際にAPIを呼んだところ、
`gemini-2.5-flash`は**新規ユーザーには提供終了しており、API自体から
`gemini-3.6-flash`へ切り替えるよう案内**されました。ドキュメント上の情報と
実際のAPIの挙動がズレていた形です。`gemini-3.6-flash`は「速度とマルチモーダル
機能のバランスを取った汎用タスク向け」の安定版(GA)モデルで、より重量級の
`gemini-3.7`/`3.8-flash`(長時間の自律エージェント・複雑なワークフロー向け)ほど
過剰ではなく、今回の単発構造化比較タスクに合っているため、こちらを最終的に
採用しています。

より軽量な`-flash-lite`系モデルも検討しましたが、複数比較軸にまたがる説明文生成・
優劣判定は単純な分類タスクより一段階複雑なため、Claude選定時(`Sonnet`を選び
`Haiku`を見送った判断)と同じ理由で、速度/コストを最優先した最軽量モデルは避けました。

**教訓**: LLM APIのモデルラインナップ・提供状況はドキュメントの記述より速く変わりうる。
コードに組み込む前に、実際に1回APIを呼んで確認するPoCの価値が実際にありました。

### PoC: ネストしたPydantic Structured Outputの動作確認

`google-genai` SDKには、ネストしたPydanticモデル(今回の`ComparisonReportResult`の
ような親子構造)を`response_schema`に渡した際の既知の不具合報告があるため、
本実装に着手する前に`backend/scripts/poc_gemini_structured_output.py`で
実際に1回だけAPIを呼び出し、動作を確認してから置き換えを行いました
(結果: 問題なく動作し、`response.parsed`が検証済みのネスト構造インスタンスとして
返ってきました。上記の通りモデル名の見直しも同時に必要になりました)。

## Structured Output

LLMの自由文をそのまま保存せず、Pydanticスキーマ(`app/services/llm_schemas.py`)で
以下の形を強制しています。

```json
{
  "recommendation": {
    "winner": "item_a",
    "summary": "...",
    "reason": "..."
  },
  "comparisons": [
    {
      "criterion": "development_speed",
      "criterion_label": "開発速度",
      "item_a_summary": "...",
      "item_b_summary": "...",
      "item_a_score": 5,
      "item_b_score": 4,
      "winner": "item_a"
    }
  ]
}
```

`winner`はユーザー向け表示のような技術名の文字列ではなく、`item_a`/`item_b`/`tie`の
Enumにしています。理由: LLMが返す文字列が技術名と完全一致する保証がなく
(表記ゆれ等)、DB保存・比較ロジックの両方で扱いづらくなるためです。表示時に
Frontend側で`research.item_a`/`item_b`に読み替えます。

`score`(1〜5)は採用しています。実装コストがほぼゼロな一方、比較表での視覚的な
優劣表示や将来のAI Evaluation(Comparison Completeness等)の材料になるためです。

## 設計上の判断メモ

### なぜ `status` にPostgreSQLのENUM型を使わないか

Python/Pydantic側 (`app/schemas/research.py` の `ResearchStatus`) で許容値を
`Enum`として明確に定義し、DB側はシンプルな文字列カラム + `CHECK`制約
(`app/models/research.py`)にとどめています。PostgreSQL固有のENUM型は値の
追加・変更に`ALTER TYPE`が必要になり、開発初期で頻繁に値を見直す可能性がある
今のフェーズでは保守コストが見合わないためです。

### なぜPhase 2からAlembicを導入したか

Phase 1はテーブル1つだけでしたが、Phase 2では既存の`researches`テーブルに
列を追加し、新しく`comparisons`テーブルを作る必要がありました。
`Base.metadata.create_all()`は「まだ存在しないテーブル」を作るだけで、
既存テーブルへの列追加を検知・反映できません。そのため、既存の開発DB
(create_all()で作成済み)を「初期migration適用済み」として`alembic stamp`し、
そこから先の変更をmigrationとして記録・適用する方式に切り替えました。
既存データ(Phase 1で作成したResearch)は壊していません。

なお、使い捨てのSQLite(pytestの一時DB)は毎回migrationを流す価値がないため、
`app/main.py`の起動時ロジックでSQLite利用時のみ`create_all()`にフォールバックし、
PostgreSQL利用時はAlembicのmigrationに一本化しています。

### Recommendationを別テーブル/JSON列にしなかった理由

`researches`テーブルに`recommendation_winner`/`summary`/`reason`を直接列として
追加しました。Recommendationは1 Researchにつき必ず1つだけ存在する1対1の関係で、
別テーブルに分離する明確な理由(複数保持・独立したクエリ対象にする必要)が
ないためです。

### 比較軸(criteria)をJSONB列にした理由

`researches.criteria`は`JSON().with_variant(JSONB, "postgresql")`という
SQLAlchemyの標準パターンを使っています。PostgreSQL上では実際にJSONB
(バイナリ格納・高速検索が可能なPostgreSQL独自の型)が使われ、テスト用の
SQLiteでは汎用JSON型にフォールバックします。検討したPostgreSQLのARRAY型は
テストで使っているSQLiteが正式にサポートしておらず、別テーブル(多対多)は
「比較軸は固定候補からの選択のみで独立してクエリする必要がない」現時点の
要件に対してオーバーエンジニアリングと判断しました。

### `BackgroundTasks` について(重要な設計上の制限)

Research処理(LLM呼び出し・比較生成)はFastAPIの`BackgroundTasks`で非同期化して
います。ただし以下の限界があります。

- **durable(永続的)なジョブキューではない**。サーバープロセスのメモリ内で
  実行されるため、**サーバーが再起動・クラッシュすると実行中のタスクは失われ、
  Researchのstatusが`pending`や`researching`のまま止まってしまう**。
- 実行状況の再試行(リトライ)やキューイングの仕組みは持たない。
- 複数サーバーインスタンスでの水平スケールを想定していない。

本格運用ではCelery / RQ / クラウドキュー等が候補になりますが、現在の規模
(個人開発のポートフォリオ)では過剰な複雑さになるため、Phase 2では導入しません。

## 秘密情報の扱い

- `.env` / `.env.local` はGit管理対象外です(`.gitignore`参照)。
- `.env.example` / `.env.local.example` には変数名のみを記載しています。
- `GEMINI_API_KEY`を含む秘密情報は、コード・ログ・README・commitのいずれにも
  実際の値を書き込みません。

## 既知の制限 (Phase 2時点)

- 比較結果は外部情報源によるGroundingがされていない(冒頭の注意書き参照)。
- Web検索・Source取得・Evidence・Citationは未実装(Phase 3で追加予定)。
- AI Evaluation、History画面、Authentication、Cloud deploymentは未実装。
- `BackgroundTasks`はdurableなジョブキューではない(上記参照)。

## Phase 3に向けて

Web Search API(候補: Tavily, Brave Search API等)で取得した情報を`sources`
テーブルに保存し、LLMにはその情報を踏まえて比較させる(Grounding)。各claimに
対応する`evidences`テーブルを追加し、Evidence Viewer画面でSource
title/URL/該当箇所を確認できるようにする、という流れを予定しています。
