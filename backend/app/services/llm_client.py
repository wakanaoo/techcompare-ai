"""Google Gemini APIを呼び出し、比較結果をStructured Outputで取得するモジュール。

Phase 2ではLLM自身の知識のみを使って比較を生成する(Web検索は行わない)。
そのため生成される比較結果は外部情報源によって検証されておらず、
最終仕様ではない(README参照)。

Provider抽象化は行わない。差し替えが必要になった時点で見直せば十分なMVP規模のため、
ここではgoogle-genai SDKを直接呼び出す。
"""

from google import genai
from google.genai import types

from app.schemas.criteria import Criterion, CRITERION_LABELS
from app.services.llm_schemas import ComparisonReportResult

# 2026年9月時点で新規ユーザーが利用できる安定版Flashモデル。
# 当初はgemini-2.5-flashを想定していたが、実装前のPoC(scripts/
# poc_gemini_structured_output.py)で実際にAPIを呼んだところ
# 「新規ユーザーには提供終了、gemini-3.6-flashへ切り替えるように」と
# APIから案内されたため、こちらを採用している(詳細はREADME参照)。
MODEL = "gemini-3.6-flash"


def _build_prompt(item_a: str, item_b: str, goal: str, criteria: list[str]) -> str:
    criteria_lines = "\n".join(
        f"- key: {key}, label: {CRITERION_LABELS[Criterion(key)]}" for key in criteria
    )

    return f"""あなたはソフトウェア技術の比較調査を行うアシスタントです。
以下の2つの技術を、指定された比較軸ごとに比較してください。

技術A: {item_a}
技術B: {item_b}
利用目的: {goal}

比較軸(必ず指定されたkeyとlabelをそのまま使うこと):
{criteria_lines}

各比較軸について、それぞれの技術の説明(日本語、2〜3文)と、その軸における
優劣を表す1〜5のスコアを付けてください。スコアの意味は次の通りです:
5 = その軸において非常に優れている、3 = 平均的・可もなく不可もない、
1 = その軸において明らかに劣っている。技術Aと技術Bを独立に採点すること
(必ずしも片方が5でもう片方が1になるとは限らない)。
その上で、どちらが優れているか(item_a / item_b / tie)を判定してください。
最後に、上記の利用目的に照らした総合的なrecommendationを出してください。

注意:
- あなた自身の知識のみに基づいて回答すること。
- 事実と異なる可能性がある内容は断定を避けた表現にすること。
- 出力は指定されたスキーマの形式のみで返すこと。"""


def generate_comparison(
    item_a: str, item_b: str, goal: str, criteria: list[str]
) -> ComparisonReportResult:
    """LLMを呼び出し、検証済みのComparisonReportResultを返す。

    GEMINI_API_KEYが未設定/無効な場合や、LLM呼び出し自体が失敗した場合は
    google.genai.errorsの例外がそのまま送出される
    (呼び出し元のresearch_runner.pyでstatus=failedとして処理する)。
    """
    # GEMINI_API_KEY(またはGOOGLE_API_KEY)環境変数から自動でキーを取得する。
    client = genai.Client()
    prompt = _build_prompt(item_a, item_b, goal, criteria)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ComparisonReportResult,
        ),
    )

    result = response.parsed
    if not isinstance(result, ComparisonReportResult):
        # malformed response: スキーマに沿わない/パースできなかった場合。
        raise ValueError("LLMの応答を期待した形式に変換できませんでした(malformed response)。")
    return result
