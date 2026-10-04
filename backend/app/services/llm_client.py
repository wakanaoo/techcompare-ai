"""Google Gemini APIを呼び出し、比較結果をStructured Outputで取得するモジュール。

Phase 3の流れ(2-stage pipeline: 検索 → grounded comparison生成。
LLM呼び出し自体は1回だけ):
  1. (research_runner.py側) Tavily APIで情報源を検索し、DBに保存する
  2. この保存済みの情報源をプロンプトに含め、Gemini APIを1回呼び出して
     Structured Output形式で比較結果を生成する

このモジュールが担当するのは2の「LLM呼び出し」部分のみ。
LLMには「提供された情報源に基づいて回答すること」「情報源に記載がなければ
断定しないこと」を明示し、根拠本文そのものは生成させない
(根拠となったsourceのIDだけを選ばせる)。

Phase 5D: Retrieval Qualityについて
根拠の粒度をSource単位からchunk単位に上げた。`_format_sources()`は
各sourceの本文を`get_source_chunks()`(app/services/search_client.py)で
文単位のchunkに分割し、`[source_id-chunk_index]`という番号を振って
プロンプトに提示する。LLMは`item_a_citations`/`item_b_citations`として
`{source_id, chunk_index}`の組を選ぶだけで、chunkの本文自体は一切
生成しない(research_runner.py側が、この座標から実際のchunk文字列を
再計算してEvidenceに保存する)。Gemini呼び出し自体は引き続き1回のまま。

Phase 4.1: rate-limit resilienceについて
15ケースを連続実行するFull Evaluationで429(Too Many Requests)が多発した
実測を受けて、以下を追加している(Redis/Celery等の新規インフラは使わず、
単一プロセス内で完結させる):
  - pace_gemini_request(): Gemini APIへの連続リクエストの間に、Settings
    経由で調整可能な最小間隔を空ける。comparison生成(このモジュール)と
    LLM Judge(evaluation/judge.py)は同じGemini API利用とみなし、
    このモジュールグローバルな状態を共有してペースを揃える
    (evaluation/judge.pyから直接importして呼ばれる)。
  - _compute_backoff_seconds(): 429/503のretry待機時間を、Gemini
    APIレスポンスにRetry-Afterヘッダがあればそれを優先し、無ければ
    指数バックオフ+jitterで計算する。

Phase 5C: Suggest Points(POST /suggest-criteria)について
generate_comparison()と同じpacing/backoff/retry基盤(_generate_structured()）
を共有しつつ、リトライ回数だけ変える(補助機能であるSuggest Pointsは同期
HTTPリクエストでユーザーを待たせるため、最大2 attemptsに抑える。既存の
comparison生成側の最大3 attemptsは変更しない)。

Phase 5D-e: Claim Groundingについて
実API smoke testで、Evidenceはverbatimなのに、item_a_summary/
item_b_summaryが述べる具体的な数値が引用元のchunkと食い違う(例:
summaryは「10年以上」、引用元chunkは「15年以上」「14年」)事例が確認された。
原因は、(1)Structured Outputのフィールド順序上summaryが先・citationsが
後に生成されるため、先に書かれたsummaryの具体的な数値が事前学習知識由来
である可能性を排除できないこと、(2)従来のプロンプトが「情報源に明確な
記載がない場合は一般的な知識を参考程度に述べてもよい」と許可しており、
この「一般的な知識」と「情報源に基づく記述」が同じsummary文字列内で
区別なく混在しうることだった。対策として`_build_prompt()`のinstructions
のみを変更し、(a)summaryは引用chunkで実際に支持できる内容だけを書く、
(b)情報源間で数値が食い違う場合は数値を出さず定性的な表現に留める、
(c)情報源に記載が無い場合も一般的な知識で数値・固有の事実を補わない、
(d)recommendationはgrounded comparisonをもとにしたAIの解釈・総合判断の
層であり個々のcitationは不要、の4点を明示した。schema
(`llm_schemas.py`)・`research_runner.py`・DB schema・公開APIはいずれも
変更しない。Gemini/Tavily呼び出し回数も変更しない。prompt文言の変更だけ
では、Geminiが実際にこれに従う保証はない(unit testで確認できるのは
prompt文字列の内容のみ)。数値の論理的な包含関係(「15年以上」は「10年
以上」を否定しない等)まで判定するbackend側の検証や、本番への常時LLM
Judge導入は、効果に対する複雑性・コストの観点から今回は見送った
(README参照)。
"""

import logging
import random
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from pydantic import BaseModel

from app.core.config import settings
from app.schemas.criteria import CONTROL_CHAR_PATTERN, MAX_CRITERION_LENGTH, label_for
from app.services.llm_schemas import ComparisonReportResult, CriteriaSuggestionsResult
from app.services.search_client import SearchResultItem, get_source_chunks

# 2026年9月時点で新規ユーザーが利用できる安定版Flashモデル。
# 当初はgemini-2.5-flashを想定していたが、実装前のPoC(scripts/
# poc_gemini_structured_output.py)で実際にAPIを呼んだところ
# 「新規ユーザーには提供終了、gemini-3.6-flashへ切り替えるように」と
# APIから案内されたため、こちらを採用している(詳細はREADME参照)。
MODEL = "gemini-3.6-flash"

# Phase 5F: Observability。prompt全文・Source本文等の大量/機密テキストは
# 一切ログに出さない(research_id・attempt番号・所要時間・HTTP statusなど
# 数値・識別子のみ)。標準loggingのみを使い、新規の監視サービス・
# 構造化ロギングライブラリは導入しない。
logger = logging.getLogger(__name__)

# 明らかに一時的なエラー(5xx、429 Too Many Requests)だけを対象にした、
# ごく小さい回数のretry。実際の手動E2Eで503(Gemini側の一時的な過負荷)が
# 複数回発生したことを受けて追加した。
# 400/401/403/404等、retryしても解決しないエラーは対象外(即座に例外を送出する)。
# Celery/RQ等の本格的なジョブキューは導入せず、この関数内で完結させている。
_COMPARISON_MAX_ATTEMPTS = 3  # 初回呼び出し + 最大2回のretry

# Suggest Points(POST /suggest-criteria)用。補助機能であり、ユーザーが
# 同期HTTPリクエストを待つため、comparison生成より少ない回数に抑える
# (初回呼び出し + 最大1回のretry)。失敗した場合はsanitized errorを
# 返し、ユーザー自身がボタンを再度押して再試行できるようにする
# (frontend側、SuggestPointsPanelで対応)。
_SUGGESTION_MAX_ATTEMPTS = 2


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True  # 5xx: Gemini側の一時的な問題である可能性が高い
    if isinstance(exc, genai_errors.ClientError) and exc.code == 429:
        return True  # 429: レート制限。少し待てば成功する可能性がある
    return False


# --- Gemini APIへのペース管理(comparison生成・LLM Judge共通) ---
# 同一プロセス内でGeminiへの連続リクエストの間隔を、Settings経由で
# 調整可能な最小間隔だけ空ける。Redis/Celery等の新規インフラは使わず、
# モジュールグローバルな「最後にリクエストした時刻」だけで実現する
# (このMVPは単一プロセス・逐次実行が前提のため、これで十分)。
_last_gemini_request_at: float | None = None


def pace_gemini_request() -> float:
    """Gemini APIを呼び出す直前に呼ぶ。設定された最小間隔(秒)に満たなければ
    その分だけ待機する。

    comparison生成(このモジュール)・LLM Judge(evaluation/judge.py)いずれの
    呼び出しも、ここを通すことで同じGemini API利用としてペースを共有する。

    Phase 5F: Observability用に、実際に待機した秒数(待たなければ0.0)を
    返す(既存の待機ロジック自体は変更しない。呼び出し側がログに使う)。
    """
    global _last_gemini_request_at
    min_interval = settings.gemini_min_request_interval_seconds
    now = time.monotonic()
    waited = 0.0
    if min_interval > 0 and _last_gemini_request_at is not None:
        remaining = min_interval - (now - _last_gemini_request_at)
        if remaining > 0:
            time.sleep(remaining)
            waited = remaining
            now = time.monotonic()
    _last_gemini_request_at = now
    return waited


def _extract_retry_after_seconds(exc: Exception) -> float | None:
    """Gemini APIのレスポンスにRetry-After相当のヘッダがあれば、
    その秒数を返す(無ければNone)。取得できる場合はこちらを優先する。
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_backoff_seconds(attempt: int, exc: Exception) -> tuple[float, bool]:
    """次のretryまでの待機秒数と、Retry-Afterヘッダを使用したかを返す。

    Retry-Afterヘッダが取得できればそれを優先する。無ければ、
    Settings経由で調整可能な基準値による指数バックオフ(1s -> 2s -> ...)に
    jitter(0〜設定値の一様乱数)を加えた値を使う。

    Phase 5F: Observability用のログは、呼び出し側がこの戻り値をそのまま
    使うこと(再度この関数を呼び出して値を取り直さない)。jitterは
    random.uniform()による乱数のため、再度呼び出すと別の値が返り、
    実際に`time.sleep()`へ使った値とログの値が食い違ってしまう。
    """
    retry_after = _extract_retry_after_seconds(exc)
    if retry_after is not None:
        return retry_after, True
    base = settings.gemini_retry_backoff_base_seconds * (2**attempt)
    jitter = random.uniform(0, settings.gemini_retry_jitter_max_seconds)
    return base + jitter, False


def _format_sources(sources: dict[int, SearchResultItem]) -> str:
    """情報源を、chunk番号付きの形式でプロンプトへ整形する(Phase 5D)。

    各chunkに`[source_id-chunk_index]`という番号を振り、LLMには
    「どのsourceの何番目のchunkを根拠にしたか」という座標だけを選ばせる
    (chunk本文自体を生成させない。research_runner.py参照)。
    get_source_chunks()はプロンプトに渡す範囲(先頭_PROMPT_CONTENT_MAX_LENGTH
    文字)に対して決定論的にchunkを計算するため、research_runner.py側で
    同じ関数を同じcontentに対して呼べば必ず同じ番号体系になる。
    """
    lines = []
    for source_id, item in sources.items():
        chunks = get_source_chunks(item.content)
        if not chunks:
            continue
        chunk_lines = "\n".join(
            f"  [{source_id}-{chunk_index}] {chunk}"
            for chunk_index, chunk in enumerate(chunks)
        )
        lines.append(f"[source_id: {source_id}] タイトル: {item.title}\nURL: {item.url}\n{chunk_lines}")
    return "\n\n".join(lines)


def _build_prompt(
    item_a: str,
    item_b: str,
    goal: str,
    criteria: list[str],
    sources: dict[int, SearchResultItem],
) -> str:
    criteria_lines = "\n".join(
        f"- key: {key}, label: {label_for(key)}" for key in criteria
    )
    sources_text = _format_sources(sources) if sources else "(情報源が見つかりませんでした)"

    return f"""あなたはソフトウェア技術の比較調査を行うアシスタントです。
以下の2つの技術を、指定された比較軸ごとに、下記の情報源に基づいて比較してください。

技術A: {item_a}
技術B: {item_b}
利用目的: {goal}

比較軸(必ず指定されたkeyとlabelをそのまま使うこと):
{criteria_lines}

--- 情報源(Web検索結果。[source_id-chunk_index]の形式で一節ごとに番号を
振っている) ---
{sources_text}
--- 情報源ここまで ---

指示:
- 各比較軸について、それぞれの技術の説明(日本語、2〜3文)を、上記の情報源に
  基づいて書くこと。
- item_a_summary/item_b_summaryは、上記の情報源(chunk)によって実際に
  支持できる内容だけを書くこと。具体的な数値や固有の事実を述べる場合は、
  その数値・事実がcitationとして選ぶchunkに実際に書かれている場合にのみ
  書くこと。情報源に無い数値・固有の事実を、一般的な知識や事前学習知識で
  補って書かないこと。
- 複数の情報源で具体的な数値が食い違う場合は、無理にどちらか1つの数値を
  採用しないこと。情報源で安全に支持できる定性的な表現(例:「長年の実績が
  ある」等、数値を伴わない表現)に留めること。
- item_a_summaryの根拠にした一節を、[source_id-chunk_index]の番号から
  {{source_id, chunk_index}}の組としてitem_a_citationsに、item_b_summaryの
  根拠はitem_b_citationsに、それぞれリストで挙げること。表示されている
  番号をそのまま使うこと(存在しないsource_id・chunk_indexを作り出さない
  こと)。1つのsummaryにつき、根拠にした一節が複数あれば複数件挙げてよい。
- 上記の情報源にその技術・比較軸についての明確な記載がない場合は、
  item_a_citations(またはitem_b_citations)を空リストにし、summary内で
  「提供された情報源には明確な記載がありません」と明示すること。この場合、
  一般的な知識で具体的な数値・固有の事実を補わないこと(断定を避けた
  一般的な説明に留め、scoreは極端な値(5または1)を避けて3(平均的)を
  基本にすること)。
- 技術Aと技術Bのスコアは独立に採点すること(必ずしも片方が5でもう片方が1に
  なるとは限らない)。スコアの意味: 5 = その軸において非常に優れている、
  3 = 平均的・可もなく不可もない、1 = その軸において明らかに劣っている。
- 最後に、上記の利用目的に照らした総合的なrecommendationを出すこと。
  recommendationは、各比較軸で得られた(情報源に基づく)比較結果をもとに
  AIが解釈・総合判断する層であり、個々のcitationを挙げる必要はない。
  こちらも各比較軸の結果に基づき、根拠が薄い場合は断定を避けること。
- 出力は指定されたスキーマの形式のみで返すこと。"""


def _generate_structured(
    client: genai.Client,
    prompt: str,
    response_schema: type[BaseModel],
    max_attempts: int,
    request_label: str,
) -> BaseModel:
    """Gemini APIをstructured outputで呼び出す共通処理。

    pace_gemini_request()によるペース管理、429/503のretry(指数バックオフ+
    jitter、Retry-Afterヘッダ優先)、malformed responseの検出をここに
    集約する。呼び出し元(generate_comparison() / generate_criteria_
    suggestions())は、response_schemaとmax_attemptsだけを渡して使い分ける
    (Suggest Pointsはユーザーが同期HTTPリクエストを待つ補助機能のため、
    comparison生成より少ないmax_attemptsを渡す。既存のcomparison生成側の
    挙動・回数はこの共通化によって変えない)。

    Phase 5F: Observability。`request_label`(例: "comparison"/"suggestion")
    はログ出力のためだけの識別子で、挙動には一切影響しない。ログには
    attempt番号・pacing待機秒数・request自体の所要時間・成功/失敗・
    HTTP status・(retryする場合)Retry-Afterを使用したか・backoff秒数を
    出す。これらはいずれも既存のロジックが**1回だけ計算・使用した値**を
    そのままログに使う(ログ出力のために`_compute_backoff_seconds()`等を
    再度呼び出すことはしない。jitterの乱数が再抽選され、実際にsleepへ
    使った値とログの値が食い違ってしまうため)。promptの内容やSource本文
    等はログに出さない。
    """
    for attempt in range(max_attempts):
        pacing_wait_seconds = pace_gemini_request()
        attempt_start = time.monotonic()
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            duration_seconds = time.monotonic() - attempt_start
            logger.info(
                "gemini_request request_type=%s attempt=%d/%d pacing_wait_s=%.2f "
                "duration_s=%.2f outcome=success",
                request_label,
                attempt + 1,
                max_attempts,
                pacing_wait_seconds,
                duration_seconds,
            )
            break
        except (genai_errors.ServerError, genai_errors.ClientError) as exc:
            duration_seconds = time.monotonic() - attempt_start
            status_code = getattr(exc, "code", "unknown")
            is_last_attempt = attempt == max_attempts - 1
            if not _is_retryable_error(exc) or is_last_attempt:
                logger.warning(
                    "gemini_request request_type=%s attempt=%d/%d pacing_wait_s=%.2f "
                    "duration_s=%.2f outcome=failure status=%s",
                    request_label,
                    attempt + 1,
                    max_attempts,
                    pacing_wait_seconds,
                    duration_seconds,
                    status_code,
                )
                raise
            # 1回だけ計算し、同じ値をログとtime.sleep()の両方に使う
            # (再計算するとjitterが再抽選され、ログと実際の待機秒数が
            # 食い違うため)。
            backoff_seconds, used_retry_after = _compute_backoff_seconds(attempt, exc)
            logger.warning(
                "gemini_request request_type=%s attempt=%d/%d pacing_wait_s=%.2f "
                "duration_s=%.2f outcome=failure status=%s retry_after_used=%s "
                "backoff_s=%.2f",
                request_label,
                attempt + 1,
                max_attempts,
                pacing_wait_seconds,
                duration_seconds,
                status_code,
                used_retry_after,
                backoff_seconds,
            )
            time.sleep(backoff_seconds)

    result = response.parsed
    if not isinstance(result, response_schema):
        # malformed response: スキーマに沿わない/パースできなかった場合。
        raise ValueError("LLMの応答を期待した形式に変換できませんでした(malformed response)。")
    return result


def generate_comparison(
    item_a: str,
    item_b: str,
    goal: str,
    criteria: list[str],
    sources: dict[int, SearchResultItem],
) -> ComparisonReportResult:
    """LLMを1回(一時的なエラー時は最大2回まで追加でretryして)呼び出し、
    検証済みのComparisonReportResultを返す。

    sources: {DB上のsource id: SearchResultItem} の辞書。
    GEMINI_API_KEYが未設定/無効な場合や、retryしても解決しない場合は
    google.genai.errorsの例外がそのまま送出される
    (呼び出し元のresearch_runner.pyでstatus=failedとして処理する。
    生のエラー内容やAPIキーはそちらで露出しないようにサニタイズされる)。
    """
    # SDKの環境変数自動探索(バージョンによってGOOGLE_API_KEY/GEMINI_API_KEYの
    # どちらを見るか変わりうる)に依存せず、Settings経由で読んだキーを明示的に渡す。
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_prompt(item_a, item_b, goal, criteria, sources)
    return _generate_structured(
        client, prompt, ComparisonReportResult, _COMPARISON_MAX_ATTEMPTS, "comparison"
    )


def _sanitize_existing_criteria_for_prompt(existing_criteria: list[str]) -> list[str]:
    """Suggest Pointsのprompt埋め込み用に、existing_criteriaを軽く正規化する。

    ここはAPI層(app/api/suggestions.py → app/services/suggestion_service.py)
    が最終的なbackend側validationを担うため、ここでは例外を送出せず、
    不正な要素(空文字・制御文字混入・長すぎる文字列)は静かに読み飛ばす
    (prompt構造への意図しない混入を防ぐ簡易的な対策)。
    """
    sanitized: list[str] = []
    for raw in existing_criteria:
        trimmed = raw.strip()
        if not trimmed or len(trimmed) > MAX_CRITERION_LENGTH:
            continue
        if CONTROL_CHAR_PATTERN.search(trimmed):
            continue
        sanitized.append(trimmed)
    return sanitized


def _build_suggestion_prompt(
    item_a: str, item_b: str, goal: str, existing_criteria: list[str]
) -> str:
    sanitized_existing = _sanitize_existing_criteria_for_prompt(existing_criteria)
    existing_lines = (
        "\n".join(f"- {c}" for c in sanitized_existing)
        if sanitized_existing
        else "(なし)"
    )

    return f"""あなたはソフトウェア技術の比較調査を支援するアシスタントです。

技術A: {item_a}
技術B: {item_b}
利用目的: {goal}

すでに比較の候補として提示されている項目(existing criteria):
{existing_lines}

指示:
- existing criteriaはすでに候補として存在するため、それと同じ、または
  明らかに重複する観点は提案しないこと。
- この利用目的だからこそ重要になる、追加または優先すべき比較ポイントを
  最大5件提案すること。
- 各提案には、名前(name。日本語、短く、体言止め程度)と、この利用目的で
  なぜ重要かの理由(reason。日本語、1文程度)を付けること。
- 意味的な類義語の判定に神経質になる必要はないが、existing criteriaと
  ほぼ同じ言い換えは避けること。
- 出力は指定されたスキーマの形式のみで返すこと。"""


def generate_criteria_suggestions(
    item_a: str,
    item_b: str,
    goal: str,
    existing_criteria: list[str],
) -> CriteriaSuggestionsResult:
    """Suggest Points(POST /suggest-criteria)用に、LLMを1回(一時的な
    エラー時は最大1回まで追加でretryして)呼び出し、検証済みの
    CriteriaSuggestionsResultを返す。

    Tavilyは呼ばない・Research/Source/Evidenceは作らない(このモジュールの
    責務はGemini呼び出しのみ)。GEMINI_API_KEYが未設定/無効な場合や、
    retryしても解決しない場合はgoogle.genai.errorsの例外がそのまま送出
    される(呼び出し元のapp/api/suggestions.pyでsanitized errorとして
    処理する)。
    """
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_suggestion_prompt(item_a, item_b, goal, existing_criteria)
    return _generate_structured(
        client, prompt, CriteriaSuggestionsResult, _SUGGESTION_MAX_ATTEMPTS, "suggestion"
    )
