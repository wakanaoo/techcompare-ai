"""Phase 4: AI Evaluation。

本番と同じ `app.services.research_runner.run_research()` を、固定の
Evaluation Set(15件)に対して実行し、
  - ルールベースmetrics(DBに保存された結果から機械的に計算できるもの)
  - LLM Judgeによるsemantic metrics(代表5件のみ)
を測定して、結果をJSON/CSVとして保存するための評価用パッケージ。

このパッケージは `app/` 配下の本番コードには一切手を入れず、あくまで
本番コードを外側から呼び出して評価するだけの立ち位置(evaluation harness)。
"""
