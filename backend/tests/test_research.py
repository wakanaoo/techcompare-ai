"""POST /research, GET /research/{id}, GET /research/{id}/result のテスト。

LLM呼び出し(app.services.research_runner.generate_comparison)は
実際のAPIを呼ばず、monkeypatchでmockに差し替える。
実LLM APIを使ったE2E確認は手動で行う(READMEの手順を参照)。
"""

from google.genai import errors as genai_errors

from app.services.llm_schemas import ComparisonReportResult

VALID_PAYLOAD = {
    "item_a": "FastAPI",
    "item_b": "Django",
    "goal": "AIアプリのバックエンドとして比較したい",
    "criteria": ["development_speed", "ai_compatibility"],
}


def _canned_result() -> ComparisonReportResult:
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
                },
                {
                    "criterion": "ai_compatibility",
                    "criterion_label": "AIアプリとの相性",
                    "item_a_summary": "FastAPIは非同期処理が得意でLLM API呼び出しと相性が良い。",
                    "item_b_summary": "DjangoもAIアプリを作れるが非同期対応は限定的。",
                    "item_a_score": 5,
                    "item_b_score": 3,
                    "winner": "item_a",
                },
            ],
        }
    )


def _mock_success(monkeypatch):
    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison",
        lambda **kwargs: _canned_result(),
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


def test_create_research_invalid_criterion_returns_422(client):
    payload = {**VALID_PAYLOAD, "criteria": ["not_a_real_criterion"]}

    response = client.post("/research", json=payload)

    assert response.status_code == 422


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


def test_research_result_not_completed_returns_409(client, monkeypatch):
    # BackgroundTasks自体を無効化し、statusをpendingのままにする。
    monkeypatch.setattr("app.api.research.run_research", lambda research_id: None)

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}/result")

    assert response.status_code == 409


def test_research_fails_when_llm_raises_generic_error(client, monkeypatch):
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
    def _unauthorized(**kwargs):
        raise genai_errors.ClientError(
            401, {"error": {"message": "API key not valid", "status": "UNAUTHENTICATED"}}
        )

    monkeypatch.setattr(
        "app.services.research_runner.generate_comparison", _unauthorized
    )

    create_response = client.post("/research", json=VALID_PAYLOAD)
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}")

    assert response.json()["status"] == "failed"
    assert "APIキー" in response.json()["error_message"]


# --- criteriaとcomparisonsの整合性検証 --------------------------------------


def test_research_fails_when_llm_returns_mismatched_criteria(client, monkeypatch):
    """LLMが要求したcriteria以外のcriterionを返した場合、保存せずfailedにする。"""

    def _mismatched_result(**kwargs):
        result = _canned_result()
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

    def _wrong_label_result(**kwargs):
        result = _canned_result()
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
