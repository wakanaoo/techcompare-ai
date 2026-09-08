"""POST /research と GET /research/{id} の基本動作を確認するテスト。"""


def test_create_research_success(client):
    response = client.post(
        "/research",
        json={
            "item_a": "FastAPI",
            "item_b": "Django",
            "goal": "AIアプリのバックエンドとして比較したい",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["item_a"] == "FastAPI"
    assert body["item_b"] == "Django"
    assert body["status"] == "pending"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_research_missing_field_returns_422(client):
    # item_b が欠けているので、Pydanticのvalidationでエラーになるはず。
    response = client.post(
        "/research",
        json={"item_a": "FastAPI", "goal": "AIアプリのバックエンドとして比較したい"},
    )

    assert response.status_code == 422


def test_get_research_success(client):
    create_response = client.post(
        "/research",
        json={
            "item_a": "PostgreSQL",
            "item_b": "MongoDB",
            "goal": "AIアプリのデータ保存として比較したい",
        },
    )
    research_id = create_response.json()["id"]

    response = client.get(f"/research/{research_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == research_id
    assert body["status"] == "pending"


def test_get_nonexistent_research_returns_404(client):
    response = client.get("/research/999999")

    assert response.status_code == 404
