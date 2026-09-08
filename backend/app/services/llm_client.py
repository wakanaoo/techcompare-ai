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
"""

import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.schemas.criteria import Criterion, CRITERION_LABELS
from app.services.llm_schemas import ComparisonReportResult
from app.services.search_client import SearchResultItem

# 2026年9月時点で新規ユーザーが利用できる安定版Flashモデル。
# 当初はgemini-2.5-flashを想定していたが、実装前のPoC(scripts/
# poc_gemini_structured_output.py)で実際にAPIを呼んだところ
# 「新規ユーザーには提供終了、gemini-3.6-flashへ切り替えるように」と
# APIから案内されたため、こちらを採用している(詳細はREADME参照)。
MODEL = "gemini-3.6-flash"

# プロンプトに含める情報源本文の長さの上限(DBには全文に近い形で保存するが、
# プロンプトに投入する量はトークン数節約のため絞る)。
_PROMPT_CONTENT_MAX_LENGTH = 800

# 明らかに一時的なエラー(5xx、429 Too Many Requests)だけを対象にした、
# ごく小さい回数のretry。実際の手動E2Eで503(Gemini側の一時的な過負荷)が
# 複数回発生したことを受けて追加した。
# 400/401/403/404等、retryしても解決しないエラーは対象外(即座に例外を送出する)。
# Celery/RQ等の本格的なジョブキューは導入せず、この関数内で完結させている。
_MAX_ATTEMPTS = 3  # 初回呼び出し + 最大2回のretry
_RETRY_BACKOFF_SECONDS = 1.0  # 1回目の待機。以降 1s -> 2s と単純に倍にする


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True  # 5xx: Gemini側の一時的な問題である可能性が高い
    if isinstance(exc, genai_errors.ClientError) and exc.code == 429:
        return True  # 429: レート制限。少し待てば成功する可能性がある
    return False


def _format_sources(sources: dict[int, SearchResultItem]) -> str:
    lines = []
    for source_id, item in sources.items():
        excerpt = item.content[:_PROMPT_CONTENT_MAX_LENGTH]
        lines.append(
            f"[ID: {source_id}] タイトル: {item.title}\nURL: {item.url}\n内容: {excerpt}"
        )
    return "\n\n".join(lines)


def _build_prompt(
    item_a: str,
    item_b: str,
    goal: str,
    criteria: list[str],
    sources: dict[int, SearchResultItem],
) -> str:
    criteria_lines = "\n".join(
        f"- key: {key}, label: {CRITERION_LABELS[Criterion(key)]}" for key in criteria
    )
    sources_text = _format_sources(sources) if sources else "(情報源が見つかりませんでした)"

    return f"""あなたはソフトウェア技術の比較調査を行うアシスタントです。
以下の2つの技術を、指定された比較軸ごとに、下記の情報源に基づいて比較してください。

技術A: {item_a}
技術B: {item_b}
利用目的: {goal}

比較軸(必ず指定されたkeyとlabelをそのまま使うこと):
{criteria_lines}

--- 情報源(Web検索結果) ---
{sources_text}
--- 情報源ここまで ---

指示:
- 各比較軸について、それぞれの技術の説明(日本語、2〜3文)を、上記の情報源に
  基づいて書くこと。
- item_a_summaryの根拠にした情報源のIDをitem_a_source_idsに、
  item_b_summaryの根拠にした情報源のIDをitem_b_source_idsに、それぞれ
  リストで挙げること。存在しないIDを作り出さないこと。
- **上記の情報源にその技術・比較軸についての明確な記載がない場合は、
  item_a_source_ids(またはitem_b_source_ids)を空リストにし、summary内で
  「提供された情報源には明確な記載がありません」と明示すること。その場合、
  一般的な知識を参考程度に述べてもよいが断定は避け、scoreは極端な値
  (5または1)を避けて3(平均的)を基本にすること。**
- 技術Aと技術Bのスコアは独立に採点すること(必ずしも片方が5でもう片方が1に
  なるとは限らない)。スコアの意味: 5 = その軸において非常に優れている、
  3 = 平均的・可もなく不可もない、1 = その軸において明らかに劣っている。
- 最後に、上記の利用目的に照らした総合的なrecommendationを出すこと。
  こちらも情報源に基づき、根拠が薄い場合は断定を避けること。
- 出力は指定されたスキーマの形式のみで返すこと。"""


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
    client = genai.Client()
    prompt = _build_prompt(item_a, item_b, goal, criteria, sources)

    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ComparisonReportResult,
                ),
            )
            break
        except (genai_errors.ServerError, genai_errors.ClientError) as exc:
            is_last_attempt = attempt == _MAX_ATTEMPTS - 1
            if not _is_retryable_error(exc) or is_last_attempt:
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))

    result = response.parsed
    if not isinstance(result, ComparisonReportResult):
        # malformed response: スキーマに沿わない/パースできなかった場合。
        raise ValueError("LLMの応答を期待した形式に変換できませんでした(malformed response)。")
    return result
