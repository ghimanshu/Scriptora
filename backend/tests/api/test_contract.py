from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_without_database():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_private_route_requires_auth():
    assert client.get("/api/v1/articles").status_code == 401


def test_commands_require_idempotency_key():
    response = client.post("/api/v1/articles", json={})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_openapi_exposes_commands_not_generic_status_patch():
    paths = app.openapi()["paths"]
    for suffix in ("submit", "resubmit", "claim"):
        assert "post" in paths[f"/api/v1/articles/{{article_id}}/{suffix}"]
    assert "/api/v1/articles/{article_id}/status" not in paths
    assert "post" in paths["/api/v1/admin/articles/{article_id}/verify-and-publish"]
