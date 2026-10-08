"""Evaluationを複数日(複数プロセス実行)に分けて実行するための、
最小限のresume state。

Free Tierの日次上限(RPD)は、固定15ケースのcomparison + Judge最大5ケース
だけでちょうど使い切ってしまい、1件のretryも許容できない(README/事後
調査参照)。そこで、Stage A(comparison生成)を複数回の実行に分けて
段階的に進められるようにする。

新規のDBテーブル・ジョブキュー・token bucket等の本格的なインフラは
追加しない(過剰設計を避ける)。1つのJSONファイル(1 run_id = 1ファイル)
へのread-modify-writeだけで完結させる。

設計のポイント:
  - Stage Aの実行結果そのものの正本(source of truth)は引き続きDB
    (Research/Comparison/Evidence)。このファイルは「どのcase_idに対して
    どのresearch_idがすでに実行済みか」というポインタだけを持つ。
  - status="completed"・status="failed"のいずれも**terminal(確定した
    最終結果)として扱い、`evaluation.run_eval.run_stage_a_cases()`は
    再実行しない**。resumeの目的は「日次RPD制限のため、まだ評価していない
    (unattempted)caseを翌日に続ける」ことに限定しており、「failed caseを
    成功するまでやり直す」ことではない。このEvaluationで測りたい
    Reliabilityは「各固定caseを、その時点の同一条件で1回評価した結果」
    であり、1 case内の最大3 attempts(既存のrequestレベルのretry)を
    使い切ってfailedになったcaseを翌日以降に再実行すると、Completion Rate
    が人工的に改善し、Run #2 / Phase 5E / Phase 5Fとの比較が不公平になる
    ため(レビューで指摘され修正)。
  - Gemini/Tavilyの実測usage(token数・呼び出し回数)もcase単位でここに
    保存する。別プロセス/別日に実行されたcaseのusageは、実行中の
    UsageRecorder(メモリ上)には乗らないため、最終的な集計
    (gemini_usage.comparison_generation等)にはこのファイルの実測値を
    正本として使う(`evaluation.run_eval.sum_stage_a_usage_from_state()`)。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).parent / "results" / "resume_state"


@dataclass
class CaseState:
    """1 case_id分の、直近の実行結果の記録。"""

    status: str  # "completed" | "failed"
    research_id: int
    gemini_call_count: int = 0
    gemini_prompt_tokens: int = 0
    gemini_candidates_tokens: int = 0
    gemini_total_tokens: int = 0
    tavily_call_count: int = 0


@dataclass
class ResumeState:
    """1回の(複数日にまたがる)Evaluation実行を束ねる状態。"""

    run_id: str
    created_at: str
    stage_a: dict[str, CaseState] = field(default_factory=dict)

    @classmethod
    def new(cls, run_id: str) -> "ResumeState":
        return cls(run_id=run_id, created_at=datetime.now(timezone.utc).isoformat())

    def completed_case_ids(self) -> set[str]:
        return {cid for cid, s in self.stage_a.items() if s.status == "completed"}

    def attempted_case_ids(self) -> set[str]:
        """completed/failedを問わず、少なくとも1回実行を試みたcase_id。"""
        return set(self.stage_a.keys())

    def record_case(self, case_id: str, case_state: CaseState) -> None:
        self.stage_a[case_id] = case_state

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "stage_a": {cid: asdict(s) for cid, s in self.stage_a.items()},
        }
        _state_path(self.run_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _state_path(run_id: str) -> Path:
    return STATE_DIR / f"{run_id}.json"


def load(run_id: str) -> ResumeState:
    """既存のstateファイルを読み込む。無ければ新規(空)のstateを返す
    (初回実行時にファイルが無いのは正常なケースであり、エラーにしない)。
    """
    path = _state_path(run_id)
    if not path.exists():
        return ResumeState.new(run_id)

    data = json.loads(path.read_text(encoding="utf-8"))
    stage_a = {
        cid: CaseState(**case_data) for cid, case_data in data.get("stage_a", {}).items()
    }
    return ResumeState(run_id=data["run_id"], created_at=data["created_at"], stage_a=stage_a)


def list_run_ids() -> list[str]:
    if not STATE_DIR.exists():
        return []
    return sorted(p.stem for p in STATE_DIR.glob("*.json"))
