from __future__ import annotations


def test_create_and_fetch_run(client, auth_headers):
    response = client.post(
        "/api/runs",
        headers=auth_headers,
        json={"area": "Silver Spring, Maryland", "notes": "Test run", "idempotency_key": "run-1"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["area"] == "Silver Spring, Maryland"
    assert payload["tasks"][0]["kind"] == "content_discovery"

    detail_response = client.get(f"/api/runs/{payload['id']}", headers=auth_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == payload["id"]
    assert detail["status"] in {"queued", "running", "completed"}


def test_knowledge_endpoint_requires_token(client):
    response = client.get("/api/knowledge")
    assert response.status_code == 401
