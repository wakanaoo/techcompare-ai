"""POST /research, GET /research/{id}, GET /research/{id}/result のテスト。

Web検索(app.services.research_runner.search_technology)とLLM呼び出し
(app.services.research_runner.generate_comparison)は実際のAPIを呼ばず、
monkeypatchでmockに差し替える。実API(Tavily/Gemini)を使ったE2E確認は
手動で行う(READMEの手順を参照)。

Phase 5Dから、1 researchあたり`search_technology`は3回呼ばれる
(item_a向け・item_b向け・比較記事向け、build_search_queries()参照)。
`_canned_sources_for()`はクエリ文字列の中身を見て、どの呼び出しかを
判別しダミーのsourceを1件返す。
"""

import logging

from google.genai import errors as genai_errors

from app.services.llm_schemas import ComparisonReportResult, EvidenceCitation
from app.services.search_client import SearchResultItem
from conftest import make_genai_api_error

VALID_PAYLOAD = {
    "item_a": "FastAPI",
    "item_b": "Django",
    "goal": "AIアプリのバックエンドとして比較したい",
    "criteria": ["development_speed", "ai_compatibility"],
}


def _canned_sources_for(query: str, **_kwargs) -> list[SearchResultItem]:
    if "vs" in query:
        label = "FastAPI vs Django Comparison"
        slug = "fastapi-vs-django"
    elif "FastAPI" in query:
        label = "FastAPI Official Docs"
        slug = "fastapi"
    else:
        label = "Django Official Docs"
        slug = "django"

    return [
        SearchResultItem(
            title=label,
            url=f"https://example.com/{slug}",
            content=f"{label}に関する公式ドキュメントの内容(テスト用ダミー本文)。",
        )
    ]


def _mock_search(monkeypatch):
    monkeypatch.setattr(
        "app.services.research_runner.search_technology",
        lambda query, **kwargs: _canned_sources_for(query, **kwargs),
    )


def _canned_result(sources: dict[int, SearchResultItem]) -> ComparisonReportResult:
    """成功時のLLM応答を模したデータ。実際に保存されたsource idを引用する。

    各ダミーsourceの本文は1文(chunk_content()で1 chunkになる)なので、
    chunk_index=0を指定すればよい。
    """
    source_ids = list(sources.keys())
    cite_a = [{"source_id": source_ids[0], "chunk_index": 0}] if source_ids else []
    cite_b_id = source_ids[1] if len(source_ids) > 1 else (source_ids[0] if source_ids else None)
    cite_b = [{"source_id": cite_b_id, "chunk_index": 0}] if cite_b_id is not None else []

    return ComparisonReportResult.model_validate(
        {
            "recommendation": {
                "winner": "item_a",
                "summary": "今回の用途ではFastAPIを推奨します",
                "reason": "非同期処理とAIアプリとの相性が良いため",
            },
            "comparisons": [
                {
                    "criterion": "development_speed",
                    "criterion_label": "開発速度",
                    "item_a_summary": "FastAPIは型ヒントを活用して高速に開発できる。",
                    "item_b_summary": "Djangoは機能が豊富だが規約が多い。",
                    "item_a_score": 5,
                    "item_b_score": 4,
                    "winner": "item_a",
                    "item_a_citations": cite_a,
                    "item_b_citations": cite_b,
                },
                {
                    "criterion": "ai_compatibility",
                    "criterion_label": "AIアプリとの相性",
                    "item_a_summary": "FastAPIは非同期処理が得意でLLM API呼び出しと相性が良い。",
                    "item_b_summary": "DjangoもAIアプリを作れるが非同期対応は限定的。",
                    "item_a_score": 5,
                    "item_b_score": 3,
                    "winner": "item_a",
                    # あえて根拠を挙げないケース(0件許容)を混ぜる。
                    "item_a_citations": [],
                    "item_b_citations": [],
                },
            ],
        }
    )


def _mock_success(monkeypatch):
    _mock_search(monkeypatch)
    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison",
        lambda **kwargs: _canned_result(kwargs["sources"]),
    )


# --- 基本的なCRUD ---------------------------------------------------------


def test_create_research_success(client, monkeypatch):
    _mock_success(monkeypatch)

    response = client.post("/research", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["item_a"] == "FastAPI"
    assert body["item_b"] == "Django"
    assert body["criteria"] == ["development_speed", "ai_compatibility"]
    # レスポンスはBackgroundTasks実行前の状態を返すため、ここではまだpending。
    assert body["status"] == "pending"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_research_missing_field_returns_422(client):
    payload = {"item_a": "FastAPI", "goal": "AIアプリのバックエンドとして比較したい", "criteria": ["development_speed"]}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_without_criteria_returns_422(client):
    payload = {**VALID_PAYLOAD, "criteria": []}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_too_many_criteria_returns_422(client):
    payload = {
        **VALID_PAYLOAD,
        "criteria": [
            "learning_curve",
            "development_speed",
            "ai_compatibility",
            "performance",
            "async_support",
            "type_safety",  # 6個 = 上限(5個)超え
        ],
    }

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_accepts_non_fixed_criterion_string(client, monkeypatch):
    """固定候補(Criterion)以外の自由入力文字列も、フォーマット要件さえ
    満たせば受け付ける(Phase 5Aで固定enumから自由入力へ変更)。"""
    _mock_success(monkeypatch)
    payload = {**VALID_PAYLOAD, "criteria": ["回答の最新性"]}

    response = client.post("/research", json=payload)

    assert response.status_code == 201
    assert response.json()["criteria"] == ["回答の最新性"]


def test_create_research_empty_criterion_returns_422(client):
    payload = {**VALID_PAYLOAD, "criteria": ["   "]}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_criterion_too_long_returns_422(client):
    payload = {**VALID_PAYLOAD, "criteria": ["a" * 41]}  # 上限41文字はNG

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_criterion_at_max_length_is_accepted(client, monkeypatch):
    _mock_success(monkeypatch)
    payload = {**VALID_PAYLOAD, "criteria": ["a" * 40]}  # 上限ちょうど40文字はOK

    response = client.post("/research", json=payload)

    assert response.status_code == 201


def test_create_research_criterion_with_newline_returns_422(client):
    payload = {**VALID_PAYLOAD, "criteria": ["development_speed\n改行を含む"]}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_duplicate_criteria_case_insensitive_returns_422(client):
    """trim後・大文字小文字を無視した重複は拒否する(固定候補と自由入力の
    組み合わせでも同様)。"""
    payload = {**VALID_PAYLOAD, "criteria": ["Development_Speed", " development_speed "]}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_rejects_fixed_key_and_its_label_as_duplicate(client):
    """固定候補のkey("cost")とlabel("コスト")は表記が異なるが意味的には
    同じcriterionなので、重複として拒否する。"""
    payload = {**VALID_PAYLOAD, "criteria": ["cost", "コスト"]}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_rejects_label_and_fixed_key_as_duplicate_reversed_order(client):
    """順序を入れ替えても(label→key)同様に重複拒否する。"""
    payload = {**VALID_PAYLOAD, "criteria": ["学びやすさ", "learning_curve"]}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


def test_create_research_trims_criterion_whitespace(client, monkeypatch):
    _mock_success(monkeypatch)
    payload = {**VALID_PAYLOAD, "criteria": ["  development_speed  ", "ai_compatibility"]}

    response = client.post("/research", json=payload)

    assert response.status_code == 201
    assert response.json()["criteria"] == ["development_speed", "ai_compatibility"]


def test_get_research_success(client, monkeypatch):
    _mock_success(monkeypatch)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == research_id


def test_get_nonexistent_research_returns_404(client):
    response = client.get("/research/999999")

    assert response.status_code == 404


# --- status遷移とLLM連携(mock) ---------------------------------------------


def test_research_completes_after_background_processing(client, monkeypatch):
    _mock_success(monkeypatch)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    # TestClient配下ではBackgroundTasksはレスポンス送出までに同期実行されるため、
    # この時点でrun_researchは完了しているはず。
    response = client.get(f"/research/{research_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_research_completes_and_logs_all_three_phases(client, monkeypatch, caplog):
    """Phase 5F: Observability。completedケースでは、retrieval→
    comparison_generation→research_doneの3行がこの順で出ること、
    research_idやduration_s等の数値のみを含み、goal/criteria等の自由文は
    含まないことを確認する。"""
    _mock_success(monkeypatch)

    with caplog.at_level(logging.INFO, logger="app.services.research_runner"):
        create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    messages = [r.message for r in caplog.records]
    retrieval_logs = [m for m in messages if "phase=retrieval" in m]
    comparison_logs = [m for m in messages if "phase=comparison_generation" in m]
    done_logs = [m for m in messages if m.startswith("research_done")]

    assert len(retrieval_logs) == 1
    assert "outcome=success" in retrieval_logs[0]
    assert f"research_id={research_id}" in retrieval_logs[0]

    assert len(comparison_logs) == 1
    assert "outcome=success" in comparison_logs[0]

    assert len(done_logs) == 1
    assert "status=completed" in done_logs[0]
    assert f"research_id={research_id}" in done_logs[0]

    # research_phaseの前にretrieval、その後にcomparison_generationが来ること。
    assert messages.index(retrieval_logs[0]) < messages.index(comparison_logs[0])
    assert messages.index(comparison_logs[0]) < messages.index(done_logs[0])

    # goal(VALID_PAYLOADの自由文)等の大量/機密テキストがログに含まれないこと。
    for message in messages:
        assert VALID_PAYLOAD["goal"] not in message
        assert len(message) < 300


def test_research_logs_only_retrieval_phase_when_search_fails(client, monkeypatch, caplog):
    """Phase 5F: Observability。retrieval phaseで失敗した場合、
    comparison_generation phaseのログは一切出ないこと(到達していないため)。"""
    import tavily.errors as tavily_errors

    def _missing_key(query, **_kwargs):
        raise tavily_errors.MissingAPIKeyError()

    monkeypatch.setattr("app.services.research_runner.search_technology", _missing_key)

    with caplog.at_level(logging.INFO, logger="app.services.research_runner"):
        client.post("/research", json=VALID_PAYLOAD)

    messages = [r.message for r in caplog.records]
    retrieval_logs = [m for m in messages if "phase=retrieval" in m]
    comparison_logs = [m for m in messages if "phase=comparison_generation" in m]
    done_logs = [m for m in messages if m.startswith("research_done")]

    assert len(retrieval_logs) == 1
    assert "outcome=failure" in retrieval_logs[0]
    assert comparison_logs == []
    assert len(done_logs) == 1
    assert "status=failed" in done_logs[0]


def test_research_result_after_completion(client, monkeypatch):
    _mock_success(monkeypatch)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}/result")

    assert response.status_code == 200
    body = response.json()
    assert body["research_id"] == research_id
    assert body["recommendation"]["winner"] == "item_a"
    assert body["recommendation"]["summary"]
    assert len(body["comparisons"]) == 2
    assert body["comparisons"][0]["criterion"] == "development_speed"
    # sources(検索結果)も一覧として含まれる。
    assert len(body["sources"]) >= 1


def test_research_result_not_completed_returns_409(client, monkeypatch):
    # BackgroundTasks自体を無効化し、statusをpendingのままにする。
    monkeypatch.setattr("app.api.research.run_research", lambda research_id: None)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}/result")

    assert response.status_code == 409


def test_research_fails_when_llm_raises_generic_error(client, monkeypatch):
    _mock_search(monkeypatch)

    def _boom(**kwargs):
        raise RuntimeError("malformed response: could not parse schema")

    monkeypatch.setattr("app.services.research_runner.generate_comparison", _boom)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    status_response = client.get(f"/research/{research_id}")
    assert status_response.json()["status"] == "failed"
    assert "malformed response" in status_response.json()["error_message"]

    result_response = client.get(f"/research/{research_id}/result")
    assert result_response.status_code == 422


def test_research_fails_on_authentication_error(client, monkeypatch):
    _mock_search(monkeypatch)

    def _unauthorized(**kwargs):
        raise make_genai_api_error(
            genai_errors.ClientError, 401, "API key not valid", "UNAUTHENTICATED"
        )

    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison", _unauthorized
    )

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}")

    assert response.json()["status"] == "failed"
    assert "APIキー" in response.json()["error_message"]


def test_research_fails_when_search_raises_missing_api_key(client, monkeypatch):
    """Tavily検索が失敗した場合もstatus=failedになり、生のエラーを露出しない。"""
    import tavily.errors as tavily_errors

    def _missing_key(query, **_kwargs):
        raise tavily_errors.MissingAPIKeyError()

    monkeypatch.setattr(
        "app.services.research_runner.search_technology", _missing_key
    )

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}")

    assert response.json()["status"] == "failed"
    assert "検索APIキー" in response.json()["error_message"]


# --- criteriaとcomparisonsの整合性検証 --------------------------------------


def test_research_fails_when_llm_returns_mismatched_criteria(client, monkeypatch):
    """LLMが要求したcriteria以外のcriterionを返した場合、保存せずfailedにする。"""
    _mock_search(monkeypatch)

    def _mismatched_result(**kwargs):
        result = _canned_result(kwargs["sources"])
        # "ai_compatibility"ではなく余分な"cost"を返してしまうケースを再現。
        result.comparisons[1].criterion = "cost"
        result.comparisons[1].criterion_label = "コスト"
        return result

    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison", _mismatched_result
    )

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    status_response = client.get(f"/research/{research_id}")
    assert status_response.json()["status"] == "failed"

    result_response = client.get(f"/research/{research_id}/result")
    assert result_response.status_code == 422


def test_comparison_label_is_determined_by_backend_not_llm(client, monkeypatch):
    """criterion_labelはLLMの出力を信用せず、backend側のCRITERION_LABELSを使う。"""
    _mock_search(monkeypatch)

    def _wrong_label_result(**kwargs):
        result = _canned_result(kwargs["sources"])
        # LLMが誤ったlabelを返しても、保存時にbackend側の正しいlabelへ矯正される。
        result.comparisons[0].criterion_label = "誤ったラベル"
        return result

    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison", _wrong_label_result
    )

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    result_response = client.get(f"/research/{research_id}/result")
    assert result_response.status_code == 200

    comparisons = result_response.json()["comparisons"]
    dev_speed = next(c for c in comparisons if c["criterion"] == "development_speed")
    assert dev_speed["criterion_label"] == "開発速度"


def test_free_text_criterion_label_equals_the_input_string(client, monkeypatch):
    """固定候補(Criterion)に無い自由入力のcriterionは、slug生成等をせず、
    入力文字列自体がcriterion_labelとしてそのまま使われる(MVP方針)。"""
    _mock_search(monkeypatch)
    custom_criteria = ["development_speed", "回答の最新性"]

    def _echo_requested_criteria(**kwargs):
        return ComparisonReportResult.model_validate(
            {
                "recommendation": {
                    "winner": "item_a",
                    "summary": "summary",
                    "reason": "reason",
                },
                "comparisons": [
                    {
                        "criterion": key,
                        # LLMが返すcriterion_labelは何であれ、backend側で矯正される。
                        "criterion_label": "LLMが返した値(無視される)",
                        "item_a_summary": "a",
                        "item_b_summary": "b",
                        "item_a_score": 4,
                        "item_b_score": 3,
                        "winner": "item_a",
                        "item_a_citations": [],
                        "item_b_citations": [],
                    }
                    for key in custom_criteria
                ],
            }
        )


    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison", _echo_requested_criteria
    )

    create_response = client.post(
        "/research", json={**VALID_PAYLOAD, "criteria": custom_criteria}
    )
    research_id = create_response.json()["id"]

    result_response = client.get(f"/research/{research_id}/result")
    assert result_response.status_code == 200

    comparisons = result_response.json()["comparisons"]
    custom = next(c for c in comparisons if c["criterion"] == "回答の最新性")
    assert custom["criterion_label"] == "回答の最新性"


# --- Phase 3: Source/Evidenceの整合性 ---------------------------------------


def test_sources_are_saved_and_returned(client, monkeypatch):
    """検索で取得したsourceがDBに保存され、resultレスポンスに含まれる。"""
    _mock_success(monkeypatch)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    result_response = client.get(f"/research/{research_id}/result")
    body = result_response.json()

    # item_a向け・item_b向け・比較記事向けで1件ずつ、計3件のsourceが
    # 保存されているはず(Phase 5D: 3クエリ)。
    assert len(body["sources"]) == 3
    titles = {s["title"] for s in body["sources"]}
    assert "FastAPI Official Docs" in titles
    assert "Django Official Docs" in titles
    assert "FastAPI vs Django Comparison" in titles


def test_evidence_is_attached_to_cited_source_only(client, monkeypatch):
    """LLMが引用したsource_idにのみEvidenceが紐づき、根拠本文はsourceの実際の内容。"""
    _mock_success(monkeypatch)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    result_response = client.get(f"/research/{research_id}/result")
    comparisons = result_response.json()["comparisons"]

    dev_speed = next(c for c in comparisons if c["criterion"] == "development_speed")
    # _canned_resultでitem_a_source_ids/item_b_source_idsを指定した比較軸には
    # Evidenceが1件以上つくはず。
    assert len(dev_speed["evidence"]) >= 1
    evidence = dev_speed["evidence"][0]
    assert evidence["source_title"]
    assert evidence["source_url"]
    # 根拠本文はLLMの自由生成ではなく、mockした検索結果の実際の内容と一致する。
    assert "公式ドキュメントの内容" in evidence["evidence_text"]

    ai_compat = next(c for c in comparisons if c["criterion"] == "ai_compatibility")
    # _canned_resultで根拠を挙げなかった比較軸は、evidence 0件を許容する。
    assert ai_compat["evidence"] == []


def test_evidence_side_reflects_which_item_it_supports(client, monkeypatch):
    """Evidence.sideはclaim文字列のパースではなく、research_runner.pyが
    item_a_source_ids/item_b_source_idsのどちらを処理していたかに基づいて
    明示的に設定する(Phase 5B)。"""
    _mock_success(monkeypatch)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    result_response = client.get(f"/research/{research_id}/result")
    comparisons = result_response.json()["comparisons"]
    dev_speed = next(c for c in comparisons if c["criterion"] == "development_speed")

    # _canned_resultはdevelopment_speedについてitem_a/item_bともに1件ずつ引用する。
    sides = {e["side"] for e in dev_speed["evidence"]}
    assert sides == {"item_a", "item_b"}


def test_evidence_with_nonexistent_source_id_is_ignored(client, monkeypatch):
    """LLMが実在しないsource_idを挙げても、Evidenceとして保存せず無視する。"""
    _mock_search(monkeypatch)

    def _hallucinated_source_id(**kwargs):
        result = _canned_result(kwargs["sources"])
        # 実在しないsource_id(存在しないはずの大きな値)を挙げてしまうケース。
        citation = EvidenceCitation(source_id=999999, chunk_index=0)
        result.comparisons[0].item_a_citations = [citation]
        result.comparisons[0].item_b_citations = [citation]
        return result

    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison", _hallucinated_source_id
    )

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    # 不正なsource_idがあっても、research全体は失敗させず正常完了する。
    status_response = client.get(f"/research/{research_id}")
    assert status_response.json()["status"] == "completed"

    result_response = client.get(f"/research/{research_id}/result")
    comparisons = result_response.json()["comparisons"]
    dev_speed = next(c for c in comparisons if c["criterion"] == "development_speed")
    # 存在しないsource_idへのEvidenceは作られない。
    assert dev_speed["evidence"] == []


def test_evidence_with_out_of_range_chunk_index_is_ignored(client, monkeypatch):
    """LLMが実在するsource_idでも範囲外のchunk_indexを挙げた場合、
    Evidenceとして保存せず無視する(Phase 5D)。"""
    _mock_search(monkeypatch)

    def _out_of_range_chunk(**kwargs):
        result = _canned_result(kwargs["sources"])
        source_id = next(iter(kwargs["sources"]))
        # ダミーsourceの本文は1文(chunkは1件、index 0)しかないため、
        # index 5は必ず範囲外になる。
        citation = EvidenceCitation(source_id=source_id, chunk_index=5)
        result.comparisons[0].item_a_citations = [citation]
        result.comparisons[0].item_b_citations = [citation]
        return result

    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison", _out_of_range_chunk
    )

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    status_response = client.get(f"/research/{research_id}")
    assert status_response.json()["status"] == "completed"

    result_response = client.get(f"/research/{research_id}/result")
    comparisons = result_response.json()["comparisons"]
    dev_speed = next(c for c in comparisons if c["criterion"] == "development_speed")
    assert dev_speed["evidence"] == []


def test_get_evidence_detail(client, monkeypatch):
    _mock_success(monkeypatch)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    result_response = client.get(f"/research/{research_id}/result")
    comparisons = result_response.json()["comparisons"]
    dev_speed = next(c for c in comparisons if c["criterion"] == "development_speed")
    evidence_id = dev_speed["evidence"][0]["id"]

    response = client.get(f"/evidence/{evidence_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == evidence_id
    assert body["research_id"] == research_id
    assert body["criterion_label"] == "開発速度"
    assert body["source_title"]
    assert body["source_url"]
    assert body["evidence_text"]
    # dev_speed["evidence"][0]はitem_a(FastAPI)側の引用(_canned_resultのcite_a)。
    assert body["side"] == "item_a"
    assert body["side_label"] == "FastAPI"


def test_get_nonexistent_evidence_returns_404(client):
    response = client.get("/evidence/999999")

    assert response.status_code == 404
