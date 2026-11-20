"""Multi-Agent：轻量协作，刻意不做常驻网关与角色扮演式对话。"""

from .bus import InMemoryBus, Message
from .coordinator import Coordinator
from .worker import Worker, WorkerResult

__all__ = ["InMemoryBus", "Message", "Coordinator", "Worker", "WorkerResult"]
