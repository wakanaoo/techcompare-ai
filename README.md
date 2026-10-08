# TechCompare AI

技術選定(例: FastAPI vs Django)を、複数の情報源の調査・構造化・比較・根拠提示によって
サポートするResearch & Comparison Toolです。AI/Web開発の学習ツールも兼ねています。

**現在のフェーズ: Phase 3 (Web検索による根拠付け)**

New Research画面 → `POST /research` → PostgreSQLへ保存 →
**Web検索(Tavily API)で情報源を取得・保存** → 取得した情報源を根拠として
LLM(Gemini API)を1回呼び出しStructured Outputで比較結果取得 →
PostgreSQLへ保存 → Comparison Report画面で表示、Evidence Viewerで
根拠を確認、という流れが動く状態です。

処理は「2-stage pipeline」(検索 → grounded comparison生成)と呼んでいます。
**LLM呼び出しは1回だけ**です(検索とLLM呼び出しを分離しているだけで、
LLMを2回呼んでいるわけではありません)。

> **既知の限界**: 検索結果に基づいてLLMが比較を生成しますが、LLMの回答が
> 情報源の内容を完全に正確に要約している保証はありません。Evidence Viewerで
> 必ず元の情報源(URL)も確認してください。

## 技術構成

| レイヤー | 技術 |
|---|---|
| Frontend | Next.js (App Router) / React / TypeScript |
| Backend | Python / FastAPI / Pydantic / SQLAlchemy / Alembic |
| Database | PostgreSQL (Docker Compose) |
| Web検索 | Tavily API |
| AI | Google Gemini API (`gemini-3.6-flash`, Structured Output) |
| Testing | pytest (検索・LLM呼び出しはmock) |

## ディレクトリ構成

```
.
├── docker-compose.yml   # PostgreSQLコンテナのみ定義
├── .env.example         # docker-compose用の環境変数サンプル
├── backend/              # FastAPI
│   ├── alembic/               # DB migration
│   ├── app/
│   │   ├── main.py               # アプリのエントリーポイント
│   │   ├── api/
│   │   │   ├── research.py         # POST/GET /research, GET /research/{id}/result
│   │   │   └── evidence.py         # GET /evidence/{id}
│   │   ├── models/                 # research.py, comparison.py, source.py, evidence.py
│   │   ├── schemas/                # research.py, criteria.py, evidence.py (Pydantic, API用)
│   │   ├── services/
│   │   │   ├── search_client.py     # Tavily API呼び出し(Web検索)
│   │   │   ├── llm_schemas.py       # LLM Structured Output用スキーマ
│   │   │   ├── llm_client.py        # Gemini API呼び出し
│   │   │   └── research_runner.py   # BackgroundTasksから呼ばれる処理本体
│   │   ├── db/session.py         # DB接続設定
│   │   └── core/config.py        # 環境変数の読み込み
│   ├── scripts/                  # 一度きりの検証用スクリプト(PoC)
│   ├── tests/
│   └── .env.example
└── frontend/             # Next.js
    ├── app/page.tsx                          # New Research画面
    ├── app/research/[id]/page.tsx            # Research Progress画面(polling)
    ├── app/research/[id]/result/page.tsx     # Comparison Report画面
    ├── app/evidence/[id]/page.tsx            # Evidence Viewer画面
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
cp .env.example .env   # DATABASE_URLは上のPostgreSQL設定と揃える。GEMINI_API_KEY/TAVILY_API_KEYも設定する
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head     # DBスキーマを最新化する(初回・Phase以降変更のたびに毎回)
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

### Tavily APIキーの設定(Phase 3から追加)

`backend/.env` の `TAVILY_API_KEY` に、Tavilyのアカウント作成
(https://app.tavily.com) 後に発行されるAPIキーを設定してください。
クレジットカード登録は不要です(無料プランで開始できます)。

キーが未設定/無効な場合、Researchのstatusは自動的に`failed`になり、
`error_message`にエラー内容が保存されます(サーバー自体はクラッシュしません)。

## テスト

```bash
cd backend
source venv/bin/activate
pytest -v
```

BackendのテストはPostgreSQL・GEMINI_API_KEY・TAVILY_API_KEYがなくても実行できます。
DBはテスト専用のSQLiteファイルに一時的に差し替え、Web検索
(`app.services.research_runner.search_technology`)とLLM呼び出し
(`app.services.research_runner.generate_comparison`)は`monkeypatch`でmockに
差し替えているため、テストのたびに課金・ネットワーク通信は発生しません。
実際のAPIを使った確認は手動E2Eとして行います。

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
- `alembic/versions/fec2d93e67a8_*.py` : Phase 3 migration(`sources`/`evidences`
  テーブル追加)。新規に空のPostgreSQL DBに対して`alembic upgrade head`を実行し、
  全migrationが順番に適用されて同じスキーマが再現できることを確認済み。

destructiveな変更(列やテーブルのDROPを伴うもの)はPhase 3時点でも行っていません。

## API一覧 (Phase 3時点)

| Method | Path | 説明 |
|---|---|---|
| POST | `/research` | 新しいResearchを作成し、裏でWeb検索+LLM比較処理を開始する |
| GET | `/research/{id}` | Researchのstatus等を取得する(polling用の軽量API) |
| GET | `/research/{id}/result` | 完了したResearchの比較結果を取得する(未完了時は409、失敗時は422)。各comparisonに`evidence`、レスポンス全体に`sources`を含む |
| GET | `/evidence/{id}` | 1件のEvidenceの詳細を取得する(Evidence Viewer画面用) |
| GET | `/health` | 死活監視用 |

## Database構造 (Phase 3時点)

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

sources                              -- Research 1 : N Sources(Phase 3で追加)
  id, research_id (FK -> researches.id, ON DELETE CASCADE),
  title, url,
  content (Tavily APIが実際に取得した本文。LLMの自由生成ではない),
  retrieved_at

evidences                            -- Comparison 1 : N Evidences(Phase 3で追加)
  id, comparison_id (FK -> comparisons.id, ON DELETE CASCADE),
  source_id (FK -> sources.id, ON DELETE CASCADE),
  claim (backend側で組み立てる定型文。LLMの自由生成ではない),
  evidence_text (sources.contentをそのまま複製。LLMの自由生成ではない),
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

## Web検索Provider選定(Phase 3)

**Tavily API**を採用しています。比較したのは以下の3つです(いずれも2026年9月時点、
公式ドキュメントで確認)。

| 観点 | Gemini内蔵Grounding | Tavily API | 自前HTTP取得 |
|---|---|---|---|
| 無料枠 | 月5,000件無料だが、3.x系モデルではFree Tier(課金アカウント未登録状態)では非対応。実質的に課金アカウント登録が必要 | 月1,000クレジット無料、**クレジットカード登録不要** | 検索機能自体がなく、任意の技術名には汎用的に使えない |
| Structured Outputとの併用 | tool(検索)とresponse_schemaの併用可否が公式ドキュメント上明確でない | 検索とLLM呼び出しが完全に別ステップなので影響なし | 該当なし |
| claim単位の根拠追跡 | 回答全体への`url_citation`(文字範囲)を私たちの構造に変換し直す必要がある | 検索結果の各itemに直接IDを振れるため、根拠付けの構造を完全にコントロールできる | 自由に設計できるが検索自体ができない |
| 実装の単純さ | Google内部の挙動がブラックボックス | 検索結果に本文が含まれ、自前のHTML解析が不要 | HTML取得・本文抽出を自作する必要がある |

**採用理由**: クレジットカード登録が不要な無料枠があり、検索とLLM呼び出しを
完全に分離できるため、Phase 2で作ったStructured Output実装に一切手を入れずに
拡張できました。根拠付けの構造(どの主張がどの情報源に基づくか)を、Google内蔵
Groundingの複雑な形式に頼らず、私たちが完全にコントロールできる形で設計できる
点も決め手になりました。

Brave Search APIも検討しましたが、2026年2月に無料枠が廃止されクレジットカード
登録必須の従量課金のみになったため、今回は除外しました。

### コスト・複雑さを抑えるための実装上の工夫

- `search_depth="basic"`を明示し、`auto_parameters=False`にしています。
  Tavilyの`auto_parameters`を有効にしたままだと、検索内容によっては
  勝手に`search_depth="advanced"`(2クレジット消費)に昇格することがあるため、
  明示的に`basic`(1クエリ=1クレジット消費)へ固定しています。
- 1クエリあたり最終的に採用するのは上位3件です。Tavilyへのリクエスト自体は
  Phase 5D-bから`max_results=8`に広げていますが、これは「候補プールを広げて
  再ランキングする」ためであり(詳細は後述のPhase 5D-bセクション参照)、
  採用件数・保存するSource数(1 Researchあたり最大9件)は変わりません。

> **旧版の記述について**: 以前このセクションには「1 Researchあたり最大6件の
> 情報源、最大6クレジット消費」という記述がありましたが、これは「6件の
> 情報源」と「クレジット消費」を混同した誤記でした。Tavily `basic`検索は
> クエリ1回=1クレジットであり、情報源の件数(`max_results`)自体はcrediteに
> 影響しません。Phase 3時点は1 Researchあたり2クエリ=2クレジット
> (下記「実行方法」のPhase 4 README記載、Tavily 30回/15ケースと整合)。
> この前提(`max_results`はクレジット消費に影響しない)は、Phase 5D-bで
> `max_results`を3→8に広げる際の設計判断の根拠にもなっている。ただし
> これはTavilyの料金ページの記載に基づく前提であり、料金体系の変更が
> あった場合は再確認が必要(呼び出し回数自体は3回/researchのまま変わらない
> ため、影響があるとしても限定的)。

- `include_raw_content="text"`で、ページの実際の本文(プレーンテキスト)を
  取得しています。これはLLMに自由に引用文を生成させず、Evidence Viewerで
  表示する根拠本文を「実際にWeb上にあったテキスト」にするためです
  (詳細は次のセクション参照)。

#### Phase 5D: 検索クエリにTechnology × Use Case × Comparison Pointを反映する

Phase 3時点のクエリは`"{技術名} 公式ドキュメント"`で、goal(利用目的)・
criteria(比較軸)を一切反映していなかった(Evidenceのノイズの主因の1つ)。
Phase 5Dから、1 Researchあたり**常に3クエリ**(`app/services/search_client.py::
build_search_queries()`)に固定する(criteria件数に比例させない。
5criteria×2technologies=10クエリのような設計にはしない):

| クエリ | 内容 |
|---|---|
| item_a向け | `"{item_a} {criteria labels} {goal} 公式ドキュメント"` |
| item_b向け | `"{item_b} {criteria labels} {goal} 公式ドキュメント"` |
| 比較記事向け | `"{item_a} vs {item_b} {criteria labels} {goal}"` |

goalがどれか1クエリだけに偏らないよう、3クエリすべてにcriteria/goalを
含める。criteria/goalはクエリが過度に長くならないよう決定論的に(LLMは
使わず)一定文字数で切り詰める。3クエリ分の結果はURLで重複排除してから
`Source`として保存する。1 Researchあたり2→3クレジットへの増加(15ケース
のFull Evaluationで30→45クレジット)は、Tavily無料枠(月1,000クレジット)
の範囲内。

#### Phase 5D-b: 検索結果のrankingで公式/一次情報を優先する

**きっかけ**: Phase 5Dの設計原則には「公式/一次情報の優先」を掲げていたが、
実際にFlask vs FastAPIで実API smoke testを行ったところ、クエリに`"公式ドキュメント"`という語を含めて
いるにもかかわらず、取得した9件のSourceに公式ドキュメント
(`flask.palletsprojects.com` / `fastapi.tiangolo.com`)が**1件も含まれて
いなかった**。原因は、Tavilyへのリクエスト自体が`max_results=3`(採用
件数と同じ)だったため、rankingで並べ替えても「候補プールの外」にある
公式ドキュメントを拾い上げる余地が最初から無かったこと。

**対策**: `app/services/search_client.py`で、Tavilyへリクエストする候補件数
(`_FETCH_RESULTS_PER_QUERY = 8`)と、実際に採用する件数
(`MAX_RESULTS_PER_QUERY = 3`、従来どおり)を分離した。

- Tavily呼び出し回数は**3回/researchのまま変更しない**(クエリ本文
  `build_search_queries()`も変更しない)。1クエリあたりの`max_results`を
  3→8に広げるだけ(=候補プールを広げて、再ランキングで拾える範囲を
  広げる)。
- 採用件数は従来どおり上位3件のまま(=保存するSource数・Geminiプロンプト
  に入るchunk数は変わらない)。
- 「公式/一次情報らしさ」は、`_official_source_bonus()`という新しいpure
  functionで、以下の2種類の**技術に依存しないルールのみ**を加点対象にする
  (技術ごとに公式ドメインを手動登録するテーブルは作らない):
  1. **技術名がホスト名に含まれるか**: `item_a`/`item_b`(例: "FastAPI")を
     正規化した文字列が、URLホスト名のいずれかのラベルに含まれるかを
     実行時に計算する(例: `fastapi.tiangolo.com`のラベル`"fastapi"`に
     完全一致、`docs.djangoproject.com`のラベル`"djangoproject"`が
     `"django"`を部分文字列として含む、など)。判定対象はホスト名のみで、
     パスは見ない(第三者記事のパスに技術名が含まれるだけで「公式」扱い
     しないため)。
  2. **技術非依存の汎用的なドキュメントホスティングパターン**:
     `readthedocs.io`等、多数の技術で共通して使われる配信基盤・命名規約
     (`docs.`で始まるホスト名、`/docs/`を含むパス等)。既存の集約系
     ドメインへの軽いペナルティ(`_SOFT_DEPRIORITIZED_DOMAINS`)と対になる、
     技術非依存で保守コストが技術数に比例しないリスト。
- このボーナス(上限0.15)は**Tavily自身のrelevance score(概ね0〜1)を
  置き換えるものではなく**、relevanceが拮抗している候補同士の中でのみ
  公式/一次情報を一段押し上げる弱いsignalとして扱う。relevanceの差が
  大きい場合(例: 公式ドメインのscoreが第三者ソースより0.2以上低い場合)は、
  公式ドメインであっても高relevanceの第三者ソースを追い越さない。
- ハードなフィルタではないため、第三者の比較記事・解説記事を除外することは
  しない。公式ドメインが見つからない場合は従来どおりTavily scoreベースの
  並び順のままで、公式ドメインが1件見つかった場合も残りの枠は引き続き
  通常のranking結果(第三者ソース)から選ばれる。

| | Phase 5D | Phase 5D-b |
|---|---|---|
| Tavily呼び出し回数/research | 3回 | **3回(変更なし)** |
| 1クエリあたりの`max_results` | 3 | 8(候補プールのみ拡大) |
| 1クエリあたり採用する件数 | 3 | **3(変更なし)** |
| Tavily credit/research | 3 credit | **3 creditのまま(同じ前提)** |
| 保存するSource数/research | 最大9件 | **最大9件(変更なし)** |
| Geminiプロンプトに入るchunk数 | 変更なし | **変更なし** |
| Gemini呼び出し回数/research | 1回 | **1回(変更なし)** |

#### Phase 5D-c: Query Languageの戦略(検索言語の切り分け)

Phase 5D-b実装後の実API smoke testで、Flask公式ドキュメント
(`flask.palletsprojects.com`)がcandidate pool自体に1件も入らない事例を
確認した。切り分け実験の結果、原因はrerankingではなく**日本語の
criteria/goalを含む長いクエリが、英語中心の公式ドキュメントのcandidate
retrieval自体を妨げていること**だと判明した(同内容を英語化したクエリ、
または`"Flask official documentation"`のような短い英語クエリでは、
いずれも公式ドメインが1位で返ってきた)。

対策として、3クエリの役割を分担する:

| クエリ | 役割 | 言語 |
|---|---|---|
| item_a向け | official/primary retrieval | 英語中心(技術名+固定criteriaの英語search term+`"official documentation"`) |
| item_b向け | official/primary retrieval | 英語中心(同上) |
| 比較記事向け | third-party comparison retrieval | 日本語(JP criteria label+JP goal、Phase 5D/5D-bから変更なし) |

固定criteria(`app/schemas/criteria.py::Criterion`)にのみ、1 criterionに
つき1語/1フレーズの英語search term対訳表(`CRITERION_ENGLISH_SEARCH_TERMS`)
を用意する(関連語への拡張はしない。query languageの効果とcriteria
keyword拡張の効果を混同しないため)。custom criteria(自由入力)は
正確な英訳を保証できないためitem_a/item_b向けクエリには含めず、比較
記事向けクエリにのみ日本語labelとして含める。Tavily呼び出し回数
(3回/research)・Gemini呼び出し回数(1回/research)はいずれも変更しない。
query翻訳のための追加LLM呼び出しも行わない。

実データ検証(Flask vs FastAPI)で、`flask.palletsprojects.com`が
candidate poolの生順位2位→reranking後1位、`fastapi.tiangolo.com`が
生順位4位→reranking後3位で、いずれも採用top3入りすることを確認した。

#### Phase 5D-d: Evidence Chunk Boundary(文途中で切れるEvidenceの修正)

実API smoke testで、Evidence本文(verbatim、改ざんなし)が文の途中や
Markdown表の行の途中で終わっている事例を2件確認した。原因は2つ:

1. `chunk_content()`が、単なる行折り返し(文末記号を伴わない改行)まで
   文の区切りとして扱っていた(例: `"...with the ability to scale up to\n
   complex applications."`という1文が、改行位置で2つのchunkに分断されて
   いた)。
2. `_PROMPT_CONTENT_MAX_LENGTH`(800文字)による機械的な末尾切り詰めが、
   文やMarkdown表の行の途中でSource.contentを寸断することがあり、
   `chunk_content()`がその切れ端を無条件に「完結したchunk」として返して
   いた。

対策(いずれも`app/services/search_client.py`、既存のverbatim保証・
noise filteringのロジックは変更しない):

- 区切りとして扱うのは、文末記号の直後・Markdown表の行末(`|`)の直後の
  改行・2つ以上連続する改行(段落区切り)のみとし、単なる行折り返しの
  単独改行では区切らない(`_CHUNK_BOUNDARY_PATTERN`)。
- `get_source_chunks()`が、実際に`_PROMPT_CONTENT_MAX_LENGTH`による
  truncationが発生した場合のみ、末尾chunkが文末記号/表の行末のいずれでも
  終わっていなければ、その1件を安全側に除外する。truncationが発生して
  いない場合(見出しのみの短いページ等)は、句点が無くても正常な終端として
  残す(「chunk数」ではなく「実際にtruncationが起きたか」で判断する)。

#### Phase 5D-e: Claim Grounding(prompt-onlyの最小対策)

実API smoke testで、Evidence(verbatim)自体は正しいにもかかわらず、
AI summaryが述べる具体的な数値がEvidenceの内容と食い違う事例を確認した
(例: summaryは「Flaskは10年以上の歴史」、実際に引用したEvidenceは
「15年以上」「14年」)。原因は、(1) Structured Outputのフィールド順序上
summaryが先・citationsが後に生成されるため、summaryの具体的な数値が
事前学習知識由来である可能性を排除できないこと、(2) 従来のプロンプトが
「情報源に明確な記載がない場合は一般的な知識を参考程度に述べてもよい」と
許可しており、この「一般的な知識」と「情報源に基づく記述」が同じ
summary文字列内で区別なく混在しうること。

対策として`_build_prompt()`のinstructionsのみを変更した(schema・
research_runner.py・DB schema・公開APIは変更しない。Gemini/Tavily
呼び出し回数も変更しない):

- item_a_summary/item_b_summaryは、提供されたchunkで実際に支持できる
  内容だけを書く。具体的な数値・固有の事実は、citationとして選ぶchunkに
  実際に書かれている場合にのみ書く。
- 複数の情報源で数値が食い違う場合は、無理にどちらか1つを採用せず、
  安全に支持できる定性的な表現に留める。
- 情報源に記載が無い場合も、一般的な知識で数値・固有の事実を補わない
  (旧い「参考程度に述べてもよい」という許可を削除)。
- `recommendation`は、各比較軸の(情報源に基づく)結果をもとにAIが
  解釈・総合判断する別の層であり、個々のcitationは不要、という役割
  分離を明示する(既存スキーマが元々持っていた分離を、文章として明文化)。

**この対策はprompt-onlyであり、Geminiが実際にこれに従う保証はない**
(unit testで確認できるのはprompt文字列の内容のみ)。数値の論理的な
包含関係(「15年以上」は「10年以上」を否定しない等)まで判定する
backend側の検証、claim単位でcitationを紐付けるschema再設計、本番への
常時LLM Judge導入は、効果に対する複雑性・コストの観点から見送った
(Judgeは本番Gemini呼び出しを1→2回に倍増させるため、「通常のResearch
1回あたりのGemini call数を増やさない」という方針に反する)。

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
      "winner": "item_a",
      "item_a_citations": [{"source_id": 1, "chunk_index": 0}, {"source_id": 3, "chunk_index": 2}],
      "item_b_citations": [{"source_id": 2, "chunk_index": 1}]
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

### `item_a_citations` / `item_b_citations`(Phase 3で導入、Phase 5Dでchunk単位に拡張)

**根拠本文(evidence_text)そのものはLLMに生成させません。** LLMが担うのは
「提供した情報源のうち、どのchunk(一節)を根拠にしたか」を`{source_id,
chunk_index}`という座標で選ぶことだけです。

理由: LLMに「引用文」まで自由生成させると、実際には存在しない文章を
もっともらしく作り出してしまうリスク(ハルシネーション)があります。
「どの座標を参照したか」という選択だけに役割を絞ることで、Evidence Viewerに
表示される文章は必ず実在するWebページの内容になることを保証しています。

Phase 3時点は「どのsourceを根拠にしたか」(source単位)の選択のみでしたが、
これだと`evidence_text`にsourceの全文(最大3000文字)をそのまま複製する
ことになり、claimと無関係な部分(navigationテキスト等)まで含まれてしまう
問題がありました。Phase 5Dから、`app/services/search_client.py::
get_source_chunks()`で各sourceの本文を文単位のchunkに事前分割し、LLMには
`chunk_index`まで選ばせることで、`evidence_text`を「claimを実際に支える
一節」まで絞り込んでいます。`get_source_chunks()`自体はnoise filtering
(`filter_noise()`: navigation断片・data URI/SVGの破損データ等、明らかな
ノイズ行の削除。要約や言い換えは一切しない)とchunking(`chunk_content()`:
文・改行などの自然なboundaryでの分割。soft targetであり、文の途中を
機械的に切ることはしない)の2つの独立したpure functionで構成されています。

`{source_id, chunk_index}`はLLMの応答を受け取った後、**backend側で必ず
実在するsource・範囲内のchunkか検証**しています(`research_runner.py`)。
存在しないsource_id・範囲外のchunk_indexが返ってきた場合はEvidenceを
作らず無視します(LLMが指定していないsourceを勝手に関連付けることも
しません)。実際に`evidence_text`へ保存する文字列は、LLMが返した文字列
ではなく、backend側で`Source.content`から再計算したchunkの実テキストです
(verbatimであることを保証するため)。根拠が見つからない比較軸は
`evidence`が0件になりますが、これはエラーではなく正常な状態として
扱います(無理に根拠をでっち上げさせないため)。

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
- `GEMINI_API_KEY` / `TAVILY_API_KEY`を含む秘密情報は、コード・ログ・README・
  commitのいずれにも実際の値を書き込みません。
- Gemini APIおよびTavily APIのエラー発生時、生のレスポンス本文はFrontendへ
  返さず、HTTPステータスに応じた定型メッセージのみを返します
  (`research_runner.py`のエラーハンドリング参照)。

## 既知の制限

- LLMの回答が情報源の内容を完全に正確に要約している保証はない
  (Evidence Viewerで元の情報源を必ず確認する設計にしている)。実際に、
  AI summaryの具体的な数値がEvidenceの内容と食い違う事例を確認している
  (Phase 5D-e参照。prompt-onlyの対策を入れたが、効果は保証されない)。
- 情報源の取得は、技術ごとの公式ドメインを事前登録するような厳密な
  「公式サイト限定」はしていない(任意の技術名に汎用的に対応するため、
  Phase 5D-c参照)。技術名とホスト名の一致や、汎用的なdocs-hostingパターン
  への弱いranking boostで公式/一次情報を優先するに留まる。
- Tavilyが、技術によっては70〜100文字程度の非常に短いcontent/snippetしか
  返さない場合があり、該当sourceから取得できるEvidenceの文脈が乏しくなる
  ことがある(Phase 5D full pipeline smoke testで確認。上流のretrieval
  特性であり、backend側のchunk化ロジックの不具合ではない)。
- `filter_noise()`の保守的な行削除ルールは、中程度の長さのボイラープレート
  (画像キャプション等)を見逃す場合がある(同smoke testで確認)。
- AI summaryが、Evidenceの限定的な表現(例: 他技術との相対比較としての
  「やや」「若干」)を、その限定を落として断定的に言い換えてしまう
  semantic-strength driftが残る場合がある(同smoke testで確認。Phase
  5D-eのprompt対策は数値の補完を対象にしており、この種の表現の強さの
  ドリフトまでは対象にしていない)。
- Phase 5E(固定15ケースの再評価)でResearch Completion Rateが15/15→
  10/15に低下した。retry/backoff/pacingのコード自体は変更していないが、
  429/503がPhase 5Dのコード変更由来か外部要因かは未確定(Phase 5E/5F参照)。
- AI Evaluation、History画面、Authentication、Cloud deploymentは未実装。
- `BackgroundTasks`はdurableなジョブキューではない(上記参照)。

## Phase 4: AI Evaluation

`backend/evaluation/` に実装。本番コード(`app/`配下)は一切変更せず、
`app.services.research_runner.run_research()` を外側から呼び出して評価する
harness(評価用スクリプト群)という位置づけ。

### 設計方針

- 固定Evaluation Set 15件(`evaluation/dataset.py`)を、本番と全く同じ
  `run_research()` に通す。
- **ルールベースmetrics**(15件全件、追加のLLM呼び出し不要)は、
  DBに保存された`Research`/`Comparison`/`Evidence`/`Source`だけから
  機械的に計算する(`evaluation/metrics.py`)。
- **LLM Judgeによるsemantic metrics**は、15件のうち代表5件
  (`JUDGE_SAMPLE_CASE_IDS`)についてのみ、1ケース1回のGemini呼び出しで
  measureする(`evaluation/judge.py`)。文章の意味理解が必要な軸だけを
  少数サンプルのLLM Judgeで補完し、それ以外はルールベースで済ませる
  ことで、Judge呼び出し回数を最小限(5回)に抑えている。
- Evaluation Setの各ケース(item_a/item_b/goal/criteria)は「ケースの
  多様性を作るための設計」であり、期待winnerをground truthとした
  accuracy計算はしない(技術選定はgoal/criteria次第で変わるため)。

### metrics(15件全件): Reliability / Answer Quality

metricsは2種類に明確に分けている(`evaluation/metrics.py`)。failedケースを
0点としてAnswer Quality側の平均に混ぜないためで、これはFull Evaluation
Run #1で実際に発生していた不具合(後述)を踏まえた整理。

#### Reliability(分母は実行した全ケース。パイプラインが完走したか)

| Metric | 定義 |
|---|---|
| Research Completion Rate | `status=="completed"`の割合(Web検索・LLM呼び出し・schema validationいずれかの失敗も含む、パイプライン全体の完走率) |
| API failure count by type | failedケースの`error_message`から分類した失敗種別ごとの件数(例: `llm_api_error_429`) |
| Latency | `updated_at - created_at`(秒)の平均/中央値/最大 |
| API usage / call counts | Gemini/Tavilyの呼び出し回数、Geminiのtoken使用量(詳細は下記) |

「LLMが不正なsource_idを何個生成したか」は測定対象にしていない
(除去ロジック自体は`tests/test_research.py`の既存unit testで担保済みで、
評価としての価値が低いと判断したため)。

Gemini API使用量(上表「API usage / call counts」の詳細): 文字数からの
概算はせず、`GenerateContentResponse.usage_metadata`
(prompt_token_count / candidates_token_count / total_token_count)を
実際のAPI呼び出しの戻り値からそのまま読み取る
(`evaluation/usage_capture.py`)。本番コードは変更せず、評価スクリプト
実行中だけ`genai.Client`を薄いラッパーに差し替えて計測する。
`call_count`は**usage_metadataを取得できた成功レスポンス数**であり、
429/503等で失敗したattemptを含む全試行回数ではない点に注意。

#### Answer Quality(分母はcompletedケースのみ。failedは含めない)

| Metric | 定義 |
|---|---|
| Comparison Completeness | 返ってきたComparison件数が要求criteria数と一致する割合 |
| Evidence Coverage | (criterion × side)の組のうちEvidenceが1件以上ある割合 |
| Source Utilization | 取得したSourceのうちEvidenceで引用された割合 |
| Recommendation Consistency | 各criterionのComparison.winner多数決とRecommendation.winnerの整合率(多数決が拮抗しているケースは判定対象外) |
| LLM Judge metrics | 代表5件についてEvidence Correctness / Unsupported Claimを判定する(詳細は下記) |

LLM Judge metrics(上表の詳細。代表5件、Gemini呼び出し最大5回): 1ケース
1回のstructured output呼び出しの中で、その回に含まれる全(criterion ×
side)claimをまとめて判定する。Judgeが実際に成功したケースのclaimsだけを
分母にする:

- **has_evidence=true(Evidence Correctness)**: 実際のComparisonの
  `item_a_summary`/`item_b_summary`が、紐づくEvidence本文(=Source.content)
  によってどれだけ裏付けられているか(supported / partially_supported / unsupported)。
  LLM-as-a-Judgeによる主観的な判定であり、正解ラベルに基づく
  accuracyではない。
- **has_evidence=false(Unsupported Claim)**: 引用元が無いにも関わらず
  summaryが根拠なく断定的な主張をしていないか。

1ケースのJudge失敗(一時的なAPIエラー等)でEvaluation全体は止めない
(`run_eval.py`が例外を捕捉し、失敗ケースとして記録した上で次のケースへ
進む)。

### Phase 4.1: rate-limit resilience

Full Evaluation Run #1(15ケース連続実行)でGemini APIの429(Too Many
Requests)が多発したことを受け、`app/services/llm_client.py`に以下を追加
(Redis/Celery等の新規インフラは使わず、単一プロセス内で完結):

- `pace_gemini_request()`: Gemini APIへの連続リクエストの間に、Settings
  経由で調整可能な最小間隔(既定15秒。当初は4秒だったが、Phase 5Gで
  Free Tierの実測RPM上限に対して安全マージンが無いことが判明し変更した。
  詳細は後述のPhase 5G参照)を空ける。comparison生成
  (本番コード)とLLM Judge(`evaluation/judge.py`)は同じGemini API利用
  とみなし、同じペース管理を共有する。
- 429/503のretry待機時間は、レスポンスにRetry-Afterヘッダがあれば
  それを優先し、無ければ指数バックオフ+jitterで計算する
  (`_compute_backoff_seconds()`)。400/401/403/404等はretryしない
  (既存方針を維持)。

### Evaluation結果: Run #1(Baseline)と Run #2(rate-limit resilience改善後)

| Reliability | Run #1(Baseline) | Run #2 |
|---|---|---|
| Research Completion Rate | 46.7%(7/15) | **100%(15/15)** |
| 失敗種別 | `llm_api_error_429` × 8 | なし |
| Latency mean / p50 / max | 3.49s / 3.65s / 5.28s | 3.74s / 3.63s / 5.26s |
| Gemini comparison-generation 成功レスポンス数 | 7 | 15 |
| Gemini Judge requested/succeeded/failed/not-eligible | 5 / 0 / 3 / 2 | 5 / **4** / 1 / 0 |

**この改善(46.7%→100%)は、pacing/backoff/jitterの追加によるpipeline
reliabilityの改善であり、LLMの回答精度(AI accuracy)が上がったことを
意味しない。** Run #2では15ケースすべてでcomparison-generationの
successful responseを取得した。ただし`call_count`はusage_metadataを
取得できた成功レスポンス数であり、失敗attemptを含まないため、各ケースが
初回attemptで成功したことまでは示さない。

| Answer-quality(completedケースのみ) | Run #1 | Run #2 |
|---|---|---|
| Comparison Completeness | 1.0 | 1.0 |
| Evidence Coverage | 0.702 | 0.716 |
| Source Utilization | 0.548※ | 0.733 |
| Recommendation Consistency | 0.833 | 0.786 |

※Run #1のBaselineファイルにはPhase 4.1修正前の計算(failedケースを
0として混入)による値が記録されているため、修正後の計算方法(completed
ケースのみ)でRun #1のcompleted 7件から再計算した値を掲載している。

LLM Judge(Run #2、Judge成功4/5ケース。Evidence Correctnessは
LLM-as-a-Judgeによる主観的判定であり、正解ラベルに基づくaccuracyでは
ない):

- Evidence-present claims(has_evidence=true、母数17件): supported 15件 /
  partially_supported 2件 / unsupported 0件
- Evidence-absent claims(has_evidence=false、母数5件): supported
  (=適切に断定を回避) 5件 / unsupported 0件

Run #1はJudgeが0/5成功(3件API失敗・2件Stage A未完了でnot-eligible)の
ため、Evidence Correctness/Unsupported Claimのデータ自体を取得できて
いない。

生のJSON/CSV結果ファイルはGitにコミットしていない
(`backend/evaluation/results/`は`.gitignore`対象)。

### Evaluation結果: Phase 5E(Phase 5D適用後の再評価)

Phase 5D(5D-a〜5D-e)適用後、Run #2と比較可能な条件(同じ固定15ケース、
同じ`JUDGE_SAMPLE_CASE_IDS`、同じmetrics定義。`evaluation/dataset.py`・
`evaluation/metrics.py`・`evaluation/judge.py`はいずれもPhase 4.1時点から
無変更)で、Full Evaluationを1回実行した。

| Reliability | Run #2 | Phase 5E |
|---|---|---|
| Research Completion Rate | 100%(15/15) | **66.7%(10/15)** |
| 失敗種別 | なし | `llm_api_error_503`×2, `llm_api_error_429`×3 |
| Latency mean / p50 / max | 3.74s / 3.63s / 5.26s | 7.83s / 7.49s / 10.88s |
| Gemini comparison-generation 成功レスポンス数 | 15 | 10 |
| Gemini Judge requested/succeeded/failed/not-eligible | 5 / 4 / 1 / 0 | 5 / **1** / 2 / 2 |
| Tavily call数 | 30(2クエリ/research、旧設計) | 45(3クエリ/research、Phase 5D-aによる意図的な設計変更。品質の劣化ではない) |

| Answer-quality(completedケースのみ) | Run #2 | Phase 5E |
|---|---|---|
| Comparison Completeness | 1.0 | 1.0 |
| Evidence Coverage | 0.716 | **0.821(改善)** |
| Source Utilization | 0.733 | **0.589(低下)** |
| Recommendation Consistency | 0.786 | 0.9(母数10件と小さい) |

LLM Judge(Evidence Correctness): Run #2は母数17件(4ケース成功)で
supported 15 / partially_supported 2 / unsupported 0(supported rate
0.882)。Phase 5Eは**Judgeが1/5ケースしか成功せず**(429で2ケース失敗、
2ケースはStage A自体が失敗しJudge対象外)、母数はわずか6件(supported
4 / partially_supported 2 / unsupported 0、supported rate 0.667)。
**母数が17件→6件、かつ判定できたケース自体が異なる(c03のみ)ため、
Phase 5D-eのclaim grounding対策の効果はこの実行結果からは比較不能。**

**事実の整理(都合よく「改善成功」とまとめない)**:
- Evidence Coverageは改善した(0.716→0.821)。
- Source Utilizationは低下した(0.733→0.589)。
- Reliabilityは429/503の多発により15/15→10/15へ低下した。
- Claim groundingの効果は、Judge成功数が17件→6件に減ったため比較不能。
- この結果を受け、Reliability低下の原因を事後に検証できるよう、
  Phase 5Fとして最小限のログ出力(Observability)を追加した。

**Reliability低下の原因調査**: retry/backoff/pacingのコード自体はRun #2
から無変更であることを確認した。429/503は既存コード上retryableに分類
されるため、失敗ケースは3回(初回+retry2回)を使い切った末に失敗したと
論理的に推測できるが、**ログが存在しないため直接確認はできなかった**。
DBのtimestamp(`Source.retrieved_at`)を使ったTavily/Gemini phase分離も
試みたが、PostgreSQLの`now()`がトランザクション開始時刻を返す仕様のため
信頼できる値にならず、分離は断念した。completedケースの平均latency
(8.19s)がRun #2比で約2.2倍に増加している一方、retryしていない
completedケースも同様に遅いことから、**latency増加の主因はretryそのもの
ではなく、Phase 5D-a/bで検索クエリ・候補プールが増えたことによる可能性が
高いと推測されるが未確定**。429/503自体がPhase 5Dのコード変更由来か、
外部(Gemini側の負荷・本セッションの累積API利用)要因かは、今回のログでは
切り分けられなかった。429/503の頻度が外部要因かコード要因かを実際に
切り分けるための再評価は、今回は実施していない。

### Phase 5F: Observability(retry/pacingの事後確認を可能にする最小ログ)

Phase 5Eの原因調査で、retry試行回数・backoff秒数・Retry-Afterの使用
有無・Gemini/Tavily phaseの所要時間のいずれも、事後にログから確認する
手段が無いことが判明した。retry/backoff/pacingの**挙動自体は一切
変更せず**、Python標準`logging`のみで以下を追加した(新規の監視
サービス・structured loggingライブラリ・DBテーブルは導入していない):

- `app/services/llm_client.py::_generate_structured()`
  (comparison生成・Suggest Points共通): attempt番号・request種別
  (comparison/suggestion)・pacing待機秒数・request自体の所要時間・
  成功/失敗・HTTP status・Retry-Afterを使用したか・実際に適用した
  backoff秒数をログ出力する。
- `evaluation/judge.py::run_judge_for_case()`: 同様の形式でJudge呼び出し
  (retryなし)をログ出力する(評価専用コードのため、本番には出ない)。
- `app/services/research_runner.py::run_research()`: `time.monotonic()`
  (DBのtimestampには依存しない)でretrieval phase・comparison_generation
  phase・Research全体の所要時間を計測・ログ出力する。

ログには`research_id`・`case_id`・attempt番号・秒数・HTTP statusなどの
数値・識別子のみを出力し、prompt全文・Source本文・Evidence本文・goal/
criteriaの自由文は一切出力しない(回帰テストで保証)。backoff秒数・
Retry-Afterの使用有無は、既存のretry処理が1回だけ計算した値をそのまま
ログに使う(観測のために同じ計算を再度呼び出すと、jitterの乱数が
再抽選され、実際の待機秒数とログの値が食い違うため)。

`evaluation/run_eval.py`の本実行時(`python -m evaluation.run_eval`)
のみ`logging.basicConfig(level=logging.INFO)`でコンソールにログを
出す設定を追加している(pytest実行時・APIサーバー実行時の挙動には
影響しない)。

### Phase 5G: RPM/RPD対策とEvaluationのResume

Phase 5Fのログを使って429/503を調査した結果、Google AI Studioの実測で
このプロジェクトのGemini Free Tierが **RPM 5・TPM 250K・RPD 20** で
あること、過去28日の最大使用量がRPM 6/5・RPD 24/20と**実際に上限超過して
いた**ことを確認した。また、インストール済み`google-genai==1.2.0`の
コードを確認し、SDK内部に自動retryが存在しないこと(アプリ側の最大3
attemptsが唯一のretry層であり、二重retryではないこと)も確認した。
これを受けて以下を変更した(本番の比較生成ロジック自体は変更していない):

- **pacing**: `gemini_min_request_interval_seconds`の既定値を4秒→15秒に
  変更(`60 / (RPM-1)`。RPM上限そのものではなくRPM-1を分母にして安全
  マージンを確保する)。
- **Error diagnostics**: 429/503発生時、`exc.status`と`exc.details`から
  best-effortで`reason`/`quota_metric`/`quota_id`をログに追加した
  (`exc.message`・`exc.details`全体はログに出さない)。
- **EvaluationのResume**: 固定15ケースのcomparison + Judge最大5ケースが
  RPD 20をretryの余地なく使い切ってしまうため、`evaluation/run_eval.py`に
  `--run-id`/`--stage {comparison,judge}`を追加し、日をまたいで分割実行
  できるようにした(`evaluation/resume_state.py`)。**completed/failedは
  いずれもterminalとして扱い、再実行しない**(failedなケースを後日成功
  するまでやり直すとCompletion Rateが人工的に改善し、Run #2 / Phase 5E /
  Phase 5Fとの比較可能性が壊れるため)。固定15ケース・Judge5ケースという
  標本数自体は変更していない。

```bash
python -m evaluation.run_eval --run-id 2026-10 --stage comparison --cases c01,c02,...
python -m evaluation.run_eval --run-id 2026-10 --stage judge
```

### Evaluationの限界

- Evaluation Setは固定15ケースであり、統計的に十分な標本数とは言えない。
- LLM Judgeの対象は15件中5件のみ(呼び出し回数を抑えるための設計上の
  トレードオフ)。Phase 5Eでは429により1/5しか成功せず、この少数性が
  さらに際立った。
- LLM Judge自体がLLM-as-a-Judge方式であり、判定そのものにLLMの
  バイアス・誤りが含まれうる(人手によるgold-standard評価ではない)。
- Phase 5Eで観測された429/503は、Phase 5Gの調査でRPM/RPD上限の実際の
  超過が確認された(前述Phase 5G参照)。ただし429がRPM/RPD/TPMのどれに
  起因するかの個別切り分け(Phase 5G追加のError diagnostics)は、次回
  実際に429/503が発生するまで実データで検証できていない。

### 実行方法

```bash
cd backend && source venv/bin/activate
pytest                       # evaluation配下のmock/unit testも含めて確認
python -m evaluation.run_eval  # 実API(Tavily/Gemini)を使った、1プロセス一括の本実行
```

Free TierのRPD上限(20)に収まらない場合は、Phase 5G追加の`--run-id`/
`--stage`オプションで日をまたいで分割実行できる(前述Phase 5G参照)。

本実行は、Evaluation Set全件分のTavily/Gemini API呼び出しを実際に行う
(既定: Tavily 45回=3クエリ/research×15、Gemini 最大20回=比較生成15+
Judge5。Tavily呼び出し回数はPhase 5D-aで2→3クエリ/researchに変更した
ため、Phase 4.1時点の30回から増えている)。結果は
`backend/evaluation/results/run_<timestamp>.json` と、
`..._cases.csv` / `..._judge_claims.csv` に保存される
(生成物なので`.gitignore`でコミット対象外にしている)。

2026年9月時点で、Baseline(Run #1)・rate-limit resilience改善後
(Run #2)・Phase 5D適用後の再評価(Phase 5E)の3回、実APIを使った
本実行を完了している(上記結果参照)。

### 今後(Phase 4スコープ外)

- Phase 5G追加のError diagnostics(status/reason/quota_metric/quota_id)
  が、次回実際に429/503が発生した際に意図通り機能するかの実データでの
  検証(ユーザーの承認を得てから、分割実行したEvaluationで確認する)。
- Phase 5D-eで見送った、claim単位でcitationを紐付けるschema再設計、
  本番への常時LLM Judge導入(コスト増を許容する判断が必要)。
- History画面: 過去のResearch一覧を表示する。
- Cloud deployment: 現状はローカル実行のみのため、デプロイ手順を整備する。
