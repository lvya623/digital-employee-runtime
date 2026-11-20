"""轻量消息总线：Multi-Agent 之间只传结构化消息，不共享可变上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Message:
    sender: str
    recipient: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryBus:
    def __init__(self) -> None:
        self._inbox: dict[str, list[Message]] = {}

    def send(self, message: Message) -> None:
        self._inbox.setdefault(message.recipient, []).append(message)

    def receive(self, recipient: str) -> list[Message]:
        return list(self._inbox.get(recipient, []))

    def all_messages(self) -> list[Message]:
        return [m for messages in self._inbox.values() for m in messages]
