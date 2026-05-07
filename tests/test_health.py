from fastapi.testclient import TestClient

from app.main import app


def test_api_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
