"""API 请求 / 响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaskIn(BaseModel):
    goal: str = "处理客户售后工单并给出处理结果"
    text: str = "商品有质量问题，希望退款"
    order_id: str = "ORD-2026-001"
    channel: str = "sms"
    human_confirmed: bool = False
    subtasks: list[dict[str, Any]] | None = None


class TaskOut(BaseModel):
    task_id: str
    status: str
    steps: list[str]
    trace_events: int
    context_report: dict[str, Any] = Field(default_factory=dict)
    message: str


class ConfirmOut(BaseModel):
    task_id: str
    status: str
    message: str
