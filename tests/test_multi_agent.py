from fastapi.testclient import TestClient

from der.api.main import app

client = TestClient(app)


def test_simple_task_is_not_delegated():
    result = client.post("/tasks/delegate", json={"text": "希望退款"}).json()
    assert result["delegated"] is False


def test_complex_task_runs_isolated_workers():
    result = client.post("/tasks/delegate", json={
        "human_confirmed": True,
        "subtasks": [
            {"goal": "处理退款", "payload": {"text": "希望退款", "channel": "sms"}},
            {"goal": "处理补发", "payload": {"text": "破损需要补发", "channel": "sms"}},
        ],
    }).json()
    assert result["delegated"] is True
    assert result["succeeded"] == 2
    assert result["degraded"] is False
    assert result["messages"] == 4
    assert len(result["workers"]) == 2


def test_failed_branch_degrades_without_blocking_others():
    result = client.post("/tasks/delegate", json={
        "human_confirmed": True,
        "subtasks": [
            {"goal": "处理退款", "payload": {"text": "希望退款", "channel": "sms"}},
            {"goal": "通知渠道异常", "payload": {"text": "破损需要补发", "channel": ""}},
        ],
    }).json()
    assert result["delegated"] is True
    assert result["succeeded"] == 1
    assert result["degraded"] is True
