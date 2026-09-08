# TechCompare AI

技術選定(例: FastAPI vs Django)を、複数の情報源の調査・構造化・比較・根拠提示によって
サポートするResearch & Comparison Toolです。AI/Web開発の学習ツールも兼ねています。

**現在のフェーズ: Phase 1 (最小 Vertical Slice)**

New Research画面 → `POST /research` → PostgreSQLへ保存 → `GET /research/{id}` →
Research Progress画面、という最小限の一本の流れだけが動く状態です。
LLM呼び出し・Web検索・比較生成・Recommendation・Evidenceは未実装です。

## 技術構成

| レイヤー | 技術 |
|---|---|
| Frontend | Next.js (App Router) / React / TypeScript |
| Backend | Python / FastAPI / Pydantic / SQLAlchemy |
| Database | PostgreSQL (Docker Compose) |
| Testing | pytest |

## ディレクトリ構成

```
.
├── docker-compose.yml   # PostgreSQLコンテナのみ定義
├── .env.example         # docker-compose用の環境変数サンプル
├── backend/              # FastAPI
│   ├── app/
│   │   ├── main.py           # アプリのエントリーポイント
│   │   ├── api/research.py   # POST/GET /research
│   │   ├── models/research.py
│   │   ├── schemas/research.py
│   │   ├── db/session.py     # DB接続設定
│   │   └── core/config.py    # 環境変数の読み込み
│   ├── tests/
│   └── .env.example
└── frontend/             # Next.js
    ├── app/page.tsx                  # New Research画面
    ├── app/research/[id]/page.tsx    # Research Progress画面
    ├── lib/api.ts                    # Backend呼び出し用クライアント
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
cp .env.example .env   # DATABASE_URLは上のPostgreSQL設定と揃える
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`http://localhost:8000/health` が `{"status": "ok"}` を返せば起動成功です。
起動時にテーブル(`researches`)が自動作成されます(Migrationについては後述)。

### 3. Frontend (Next.js) を起動する

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

`http://localhost:3000` を開き、New Research画面からResearchを作成すると
`/research/{id}` に遷移し、保存された内容が表示されます。

## テスト

```bash
cd backend
source venv/bin/activate
pytest -v
```

BackendのテストはPostgreSQLを起動していなくても実行できます
(テスト専用のSQLiteファイルに一時的に差し替えているため。詳細は `tests/conftest.py`)。

## API一覧 (Phase 1時点)

| Method | Path | 説明 |
|---|---|---|
| POST | `/research` | 新しいResearchを作成する |
| GET | `/research/{id}` | 指定したResearchを取得する |
| GET | `/health` | 死活監視用 |

## 設計上の判断メモ

### なぜ `status` にPostgreSQLのENUM型を使わないか

Python/Pydantic側 (`app/schemas/research.py` の `ResearchStatus`) で許容値を
`Enum`として明確に定義し、DB側はシンプルな文字列カラム + `CHECK`制約
(`app/models/research.py`)にとどめています。
理由: PostgreSQL固有のENUM型は値の追加・変更に`ALTER TYPE`が必要になり、
開発初期で頻繁に値を見直す可能性がある今のフェーズでは保守コストが見合わないため。
値の正しさの一次情報はPython側に置き、DB側は「明らかに不正な値が直接書き込まれる」
ことを防ぐ最低限の保険として`CHECK`制約を使っています。

### なぜAlembicを導入しないか(Phase 1時点)

**Alembicとは**: SQLAlchemyのモデル変更をDBのスキーマ変更(マイグレーション)として
記録・適用するためのツールです。「テーブルを追加する」「列を追加する」といった変更を
バージョン管理し、他の環境でも同じ手順で反映できるようにします。

**なぜ必要か**: 本来、DBスキーマは手作業で変更すると環境間で状態がズレてしまうため、
チーム開発や本番運用ではほぼ必須の仕組みです。

**今回導入しない理由**: 現時点でテーブルは`researches`1つだけで、
まだスキーマが安定していません(このあとの比較・Evidence関連テーブルの追加で
すぐに変わることが分かっています)。そのため、Phase 1では
`Base.metadata.create_all()`(アプリ起動時にテーブルがなければ作成する)という
簡易的な方法にとどめています。

**いつ導入すべきか**: テーブル構成がある程度固まった次のVertical Slice
(比較生成・Evidence関連テーブルの追加)のタイミングでAlembicを導入する予定です。
複数人での開発や本番運用を見据えるフェーズになったら必須になります。

### `recommendation` / `error_message` を今のテーブルに含めない理由

設計レビュー時点ではこの2列を追加する案もありましたが、Phase 1では
「Researchを作って読み取るだけ」であり、これらの列に値を書き込む処理が
まだ存在しません。使われない列を先に追加すると、実際に必要になった時点で
「本当にこの形でよいか」を再検証しないまま固定化してしまうリスクがあります。
そのため、実際に比較生成・エラーハンドリングを実装するタイミングで
migrationとして追加する方針にしました。

### `BackgroundTasks` について(design note、Phase 1では未使用)

将来Research処理(Web検索・LLM呼び出し・比較生成)を非同期化する際、
MVPとしてはFastAPIの`BackgroundTasks`を使う想定です。ただし以下の限界を
明記しておきます。

- サーバープロセスのメモリ内で実行されるため、**サーバーが再起動・クラッシュすると
  実行中のタスクは失われ、Researchのstatusが`pending`や`researching`のまま
  止まってしまう**。
- 実行状況の再試行(リトライ)やキューイングの仕組みは持たない。
- 複数サーバーインスタンスでの水平スケールを想定していない。

これらはCelery/Redisなどの本格的なジョブキューを使えば解決できますが、
現在の規模(個人開発のポートフォリオ、同時実行数が少ない)では過剰な複雑さになるため、
今回は導入しません。将来的にユーザー数や信頼性要件が増した場合に見直す想定です。

### なぜStructured Output系のフロー確認をこのReadmeに書いていないか

Phase 1ではLLM呼び出し自体を実装していないため、Structured Outputに関する
設計判断は次のVertical Slice以降のREADME更新で記載します。

## 秘密情報の扱い

- `.env` / `.env.local` はGit管理対象外です(`.gitignore`参照)。
- `.env.example` / `.env.local.example` には変数名のみを記載しています。
- パスワード等の実際の値はローカルの `.env` にのみ存在し、コード・ログ・READMEには
  一切書き込みません。

## 既知の制限 (Phase 1時点)

- LLM API呼び出し、Web検索、比較生成、Recommendation、Evidenceは未実装。
- Research Progress画面はページ読み込み時に1回fetchするのみで、
  自動ポーリングによる状態更新は未実装(Backgroundでの処理自体がまだ存在しないため)。
- Alembicは未導入(上記参照)。
