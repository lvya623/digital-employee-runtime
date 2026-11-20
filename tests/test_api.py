from fastapi.testclient import TestClient

from der.api.deps import get_runtime
from der.api.main import app

client = TestClient(app)


def test_health_and_skill_catalog():
    assert client.get("/health").json()["skills"] == 11
    catalog = client.get("/skills").json()["skills"]
    assert any(s["name"] == "refund" and s["risk"] == "high" for s in catalog)
    assert all(client.get("/skills/health").json().values())


def test_high_risk_flow_and_idempotent_confirmation():
    created = client.post("/tasks", json={"text": "商品有质量问题，希望退款"})
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "needs_human"
    task_id = body["task_id"]

    confirmed = client.post(f"/tasks/{task_id}/confirm")
    assert confirmed.json()["status"] == "succeeded"
    runtime = get_runtime()
    assert len(runtime.business.refunds) == 1
    assert len(runtime.business.notifications) == 1

    # 同一任务重复确认：step_id 不变 → 幂等键不变 → 不会重复退款 / 重复触达
    again = client.post(f"/tasks/{task_id}/confirm")
    assert again.json()["status"] == "succeeded"
    assert len(runtime.business.refunds) == 1
    assert len(runtime.business.notifications) == 1

    trace = client.get(f"/tasks/{task_id}/trace").json()["events"]
    assert any(e["kind"] == "task.succeeded" for e in trace)


def test_missing_task_returns_404():
    assert client.get("/tasks/not-exist").status_code == 404
    assert client.post("/tasks/not-exist/confirm").status_code == 404
