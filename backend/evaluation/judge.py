"""LLM Judge: 代表5ケースについて、Evidence Correctness / Unsupported Claim
をGemini APIで判定する。

1ケースにつきGemini呼び出しは1回だけ(そのケース内の全criterion×sideの
claimをまとめて1回のstructured output呼び出しで判定する)。
  - has_evidence=true  のclaim: 実際に引用されたEvidence本文と、
    item_a_summary/item_b_summaryそのものを比較し、Evidence Correctness
    (supported / partially_supported / unsupported)を判定する。
  - has_evidence=false のclaim: 引用元が無いにも関わらず、summaryが
    根拠なく断定的な主張をしていないか(Unsupported Claim)を判定する。

genericな`Evidence.claim`(定型文)ではなく、実際の
`Comparison.item_a_summary` / `item_b_summary` を判定対象に使う。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.llm_client import MODEL, pace_gemini_request

# Phase 5F: Observability。promptの内容・Evidence本文等はログに出さない
# (case_id・attempt・所要時間・成功/失敗・HTTP statusのみ)。
logger = logging.getLogger(__name__)


class ClaimVerdict(str, Enum):
    supported = "supported"
    partially_supported = "partially_supported"
    unsupported = "unsupported"


class ClaimJudgment(BaseModel):
    """1つの(criterion, side)claimについてのJudgeの判定。"""

    criterion: str = Field(..., description="判定対象のcriterion内部キー。指定されたキーをそのまま使うこと。")
    side: Literal["item_a", "item_b"] = Field(
        ..., description="判定対象がitem_aとitem_bどちらのsummaryか。指定された値をそのまま使うこと。"
    )
    has_evidence: bool = Field(
        ..., description="入力で与えられたhas_evidenceの値をそのまま使うこと。"
    )
    verdict: ClaimVerdict = Field(
        ...,
        description=(
            "has_evidence=trueの場合(Evidence Correctness判定): 提示した引用元本文が"
            "summaryの内容をどれだけ裏付けているかを判定すること。"
            "has_evidence=falseの場合(Unsupported Claim判定): 引用元が無いにも"
            "関わらずsummaryが根拠なく断定的な主張をしていないかを判定すること"
            "(断定的な主張をしていればunsupported、一般的に広く知られた事実や"
            "断定を避けた表現に留まっていればsupportedとする)。"
        ),
    )
    rationale: str = Field(..., description="判定理由を日本語で1〜2文")


class CaseJudgmentResult(BaseModel):
    """1ケース分のJudge結果全体。"""

    claims: list[ClaimJudgment]


@dataclass(frozen=True)
class JudgeClaimInput:
    criterion: str
    criterion_label: str
    side: Literal["item_a", "item_b"]
    summary: str
    has_evidence: bool
    evidence_texts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JudgeCaseInput:
    case_id: str
    item_a: str
    item_b: str
    goal: str
    claims: list[JudgeClaimInput]


def _build_prompt(case: JudgeCaseInput) -> str:
    lines = [
        "あなたは技術比較レポートの品質を検証するレビュアーです。",
        f"比較対象: 「{case.item_a}」と「{case.item_b}」",
        f"比較の目的: {case.goal}",
        "",
        "以下は、それぞれの比較軸(criterion)についてitem_a/item_bごとに",
        "生成された説明文(summary)の一覧です。各claimについて指示に従い判定してください。",
        "",
    ]
    for i, claim in enumerate(case.claims, start=1):
        lines.append(f"--- claim {i} ---")
        lines.append(f"criterion: {claim.criterion}({claim.criterion_label})")
        lines.append(f"side: {claim.side}")
        lines.append(f"summary: {claim.summary}")
        if claim.has_evidence:
            lines.append("has_evidence: true")
            lines.append("このsummaryの根拠として実際に引用された情報源本文:")
            for j, text in enumerate(claim.evidence_texts, start=1):
                lines.append(f"  [evidence {j}] {text}")
            lines.append(
                "上記evidenceがsummaryの内容をどれだけ裏付けているか判定すること"
                "(Evidence Correctness)。"
            )
        else:
            lines.append("has_evidence: false(この主張には引用元の情報源が1件も紐づいていません)")
            lines.append(
                "根拠が無いにも関わらず、summaryが断定的な主張をしていないか判定すること"
                "(Unsupported Claim判定)。"
            )
        lines.append("")

    lines.append(
        f"入力されたclaimは{len(case.claims)}件です。出力のclaimsも同じ{len(case.claims)}件、"
        "criterionとsideの組は入力と1対1で対応させ、過不足なく返すこと。"
    )
    return "\n".join(lines)


def run_judge_for_case(case: JudgeCaseInput) -> CaseJudgmentResult:
    """指定ケースについてGemini APIを1回呼び出し、判定結果を返す。

    リトライはしない(このJudge呼び出しは全体で5回程度の少数呼び出しであり、
    一時的なエラー時は評価スクリプト側で該当ケースをJudge対象から除外して
    記録すればよいため、本番のgenerate_comparison()のような複雑なretry
    ロジックは持たせない)。ただし、Gemini APIへのペース管理(最小リクエスト
    間隔)はcomparison生成と共有する(pace_gemini_request()参照。同じ
    Gemini API利用として、429を避けるためのペースを揃える)。

    Phase 5F: Observability。retryが無いためattemptは常に1/1。ログには
    case_id・pacing待機秒数・request自体の所要時間・成功/失敗・
    (失敗時)HTTP statusのみを出す(promptの内容・Evidence本文は出さない)。
    """
    # app.services.llm_client.generate_comparison()と同様、SDKの環境変数
    # 自動探索(バージョンによってGOOGLE_API_KEY/GEMINI_API_KEYのどちらを
    # 見るか変わりうる)に依存せず、Settings経由のキーを明示的に渡す。
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_prompt(case)
    pacing_wait_seconds = pace_gemini_request()
    attempt_start = time.monotonic()
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CaseJudgmentResult,
            ),
        )
    except (genai_errors.ServerError, genai_errors.ClientError) as exc:
        duration_seconds = time.monotonic() - attempt_start
        logger.warning(
            "gemini_request request_type=judge case_id=%s attempt=1/1 "
            "pacing_wait_s=%.2f duration_s=%.2f outcome=failure status=%s",
            case.case_id,
            pacing_wait_seconds,
            duration_seconds,
            getattr(exc, "code", "unknown"),
        )
        raise

    duration_seconds = time.monotonic() - attempt_start
    logger.info(
        "gemini_request request_type=judge case_id=%s attempt=1/1 "
        "pacing_wait_s=%.2f duration_s=%.2f outcome=success",
        case.case_id,
        pacing_wait_seconds,
        duration_seconds,
    )

    result = response.parsed
    if not isinstance(result, CaseJudgmentResult):
        raise ValueError(
            "LLM Judgeの応答を期待した形式に変換できませんでした(malformed response)。"
        )
    return result


def aggregate_judge_claims(claims: list[ClaimJudgment]) -> dict:
    """判定済みclaim一覧を、has_evidenceの有無で
    Evidence Correctness / Unsupported Claimの2グループに分けて集計する。"""

    evidence_group = [c for c in claims if c.has_evidence]
    no_evidence_group = [c for c in claims if not c.has_evidence]

    def _counts(group: list[ClaimJudgment]) -> dict:
        return {
            "supported": sum(1 for c in group if c.verdict == ClaimVerdict.supported),
            "partially_supported": sum(
                1 for c in group if c.verdict == ClaimVerdict.partially_supported
            ),
            "unsupported": sum(1 for c in group if c.verdict == ClaimVerdict.unsupported),
            "total": len(group),
        }

    evidence_counts = _counts(evidence_group)
    no_evidence_counts = _counts(no_evidence_group)

    return {
        "claims_judged_total": len(claims),
        # Evidenceありclaim: summaryが引用元によってどれだけ裏付けられているか。
        "evidence_correctness": {
            **evidence_counts,
            "supported_rate": (
                evidence_counts["supported"] / evidence_counts["total"]
                if evidence_counts["total"]
                else None
            ),
        },
        # Evidenceなしclaim: 根拠なく断定的な主張をしていないか。
        "unsupported_claim": {
            **no_evidence_counts,
            "unsupported_rate": (
                no_evidence_counts["unsupported"] / no_evidence_counts["total"]
                if no_evidence_counts["total"]
                else None
            ),
        },
    }
