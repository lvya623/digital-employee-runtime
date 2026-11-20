"""内存版业务系统替身：可替换为真实 Java/Python 订单服务，接口契约不变。

关键设计：所有带副作用的操作都必须支持幂等键与撤销，否则执行链路无法安全重试/回滚。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from der.domain.errors import NonRetryableError, RetryableError


@dataclass
class BusinessStore:
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    refunds: dict[str, dict[str, Any]] = field(default_factory=dict)
    reships: dict[str, dict[str, Any]] = field(default_factory=dict)
    replies: dict[str, str] = field(default_factory=dict)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    escalations: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    _seen: dict[str, Any] = field(default_factory=dict)
    _notified: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.orders:
            self.orders["ORD-2026-001"] = {
                "order_id": "ORD-2026-001", "customer": "林女士", "amount": 268.0,
                "status": "delivered", "items": ["降噪耳机 x1"], "paid": True,
            }
            self.orders["ORD-2026-002"] = {
                "order_id": "ORD-2026-002", "customer": "陈先生", "amount": 1299.0,
                "status": "delivered", "items": ["显示器 x1"], "paid": True,
            }

    def get_order(self, order_id: str) -> dict[str, Any]:
        if order_id not in self.orders:
            raise NonRetryableError(f"order {order_id} not found")
        return dict(self.orders[order_id])

    def refund(self, order_id: str, key: str) -> dict[str, Any]:
        """幂等退款：同一个 idempotency_key 重复调用不会产生第二笔退款。"""
        if key in self._seen:
            return dict(self._seen[key])
        order = self.get_order(order_id)
        if not order["paid"]:
            raise NonRetryableError("order is not paid")
        receipt = {"refund_id": f"RF-{key[-6:]}", "order_id": order_id,
                   "amount": order["amount"], "status": "refunded"}
        self.refunds[receipt["refund_id"]] = receipt
        self._seen[key] = receipt
        return dict(receipt)

    def undo_refund(self, key: str) -> None:
        receipt = self._seen.pop(key, None)
        if receipt:
            self.refunds.pop(receipt["refund_id"], None)

    def create_reship(self, order_id: str, key: str) -> dict[str, Any]:
        if key in self._seen:
            return dict(self._seen[key])
        order = self.get_order(order_id)
        receipt = {"reship_id": f"RS-{key[-6:]}", "order_id": order_id,
                   "items": list(order["items"]), "status": "created"}
        self.reships[receipt["reship_id"]] = receipt
        self._seen[key] = receipt
        return dict(receipt)

    def undo_reship(self, key: str) -> None:
        receipt = self._seen.pop(key, None)
        if receipt:
            self.reships.pop(receipt["reship_id"], None)

    def escalate(self, order_id: str, reason: str) -> dict[str, Any]:
        record = {"order_id": order_id, "reason": reason, "queue": "human_l2"}
        self.escalations.append(record)
        return record

    def notify(self, channel: str, content: str, key: str | None = None) -> dict[str, Any]:
        if not channel:
            raise RetryableError("notification channel temporarily unavailable")
        if key and key in self._notified:
            return dict(self._notified[key])
        record = {"channel": channel, "content": content}
        self.notifications.append(record)
        if key:
            self._notified[key] = record
        return record
