from fastapi.testclient import TestClient

from app.main import app


def test_task_crud_filters_and_completed_at() -> None:
    with TestClient(app) as client:
        first = client.post("/api/v1/tasks", json={"title": "Build API", "priority": "high", "assigned_agent_id": "developer"})
        second = client.post("/api/v1/tasks", json={"title": "Research", "assigned_agent_id": "researcher"})
        assert first.status_code == 201 and second.status_code == 201
        task_id, second_id = first.json()["id"], second.json()["id"]
        try:
            assert first.json()["status"] == "todo"
            assert client.get(f"/api/v1/tasks/{task_id}").json()["assigned_agent_id"] == "developer"
            assert len(client.get("/api/v1/tasks?limit=1&offset=0").json()) == 1
            assert len(client.get("/api/v1/tasks?limit=1&offset=1").json()) == 1
            assert second_id in [t["id"] for t in client.get("/api/v1/tasks?assigned_agent_id=researcher").json()]
            updated = client.patch(f"/api/v1/tasks/{task_id}", json={"title": "Build robust API", "description": "Details", "assigned_agent_id": None})
            assert updated.json()["title"] == "Build robust API" and updated.json()["assigned_agent_id"] is None
            done = client.patch(f"/api/v1/tasks/{task_id}/status", json={"status": "done"})
            assert done.json()["completed_at"] is not None
            assert task_id in [t["id"] for t in client.get("/api/v1/tasks?status=done").json()]
            reopened = client.patch(f"/api/v1/tasks/{task_id}/status", json={"status": "in_progress"})
            assert reopened.json()["completed_at"] is None
        finally:
            assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 204
            client.delete(f"/api/v1/tasks/{second_id}")


def test_task_validation_and_not_found() -> None:
    invalid_payloads = [
        {"title": "   "},
        {"title": "Task", "status": "working"},
        {"title": "Task", "priority": "urgent"},
        {"title": "Task", "assigned_agent_id": "unknown-agent"},
    ]
    with TestClient(app) as client:
        for index, payload in enumerate(invalid_payloads):
            response = client.post("/api/v1/tasks", json=payload)
            assert response.status_code == (404 if index == 3 else 422)
        assert client.get("/api/v1/tasks/999999999").status_code == 404
        assert client.patch("/api/v1/tasks/999999999/status", json={"status": "done"}).status_code == 404
        assert client.delete("/api/v1/tasks/999999999").status_code == 404
        assert client.get("/api/v1/agents").status_code == 200
        assert client.get("/api/v1/conversations").status_code == 200
