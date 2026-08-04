from __future__ import annotations


def test_sample_run_generates_artifacts_and_evidence(client, auth_headers):
    create_response = client.post(
        "/api/runs",
        headers=auth_headers,
        json={"area": "Towson, Maryland", "notes": "Integration", "idempotency_key": "run-2"},
    )
    assert create_response.status_code == 202
    run_id = create_response.json()["id"]

    process_response = client.post(f"/api/runs/{run_id}/process", headers=auth_headers)
    assert process_response.status_code == 200
    processed = process_response.json()

    artifact_types = {artifact["artifact_type"] for artifact in processed["artifacts"]}
    assert processed["status"] == "completed"
    assert {"executive_brief", "launch_roadmap", "launch_checklist"} <= artifact_types
    assert processed["evidence"]
    assert all("Planning-only output" in artifact["content"] for artifact in processed["artifacts"])
