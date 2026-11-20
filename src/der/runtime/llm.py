"""LLM Provider 抽象：模型与 Agent 外壳解耦，换供应商不动执行链路。"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Protocol

from der.config import Settings, settings
from der.logging_conf import get_logger


class LLMProvider(Protocol):
    def plan(self, goal: str, skill_cards: list[dict], payload: dict[str, Any]) -> dict[str, Any]:
        """把目标 + 可用能力清单 + 任务载荷，转成结构化执行计划。"""
        ...


def _strip_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


class MockLLM:
    """确定性计划生成器：不依赖任何 API Key，保证 demo / CI / 本地调试可复现。

    真实部署时替换为 OpenAICompatLLM；Planner 与 Executor 不需要改动一行。
    """

    DEFAULT_PLANS: dict[str, list[str]] = {
        "refund": [
            "classify_ticket", "fetch_order", "assess_policy", "knowledge_lookup",
            "refund", "write_reply", "notify", "audit_log",
        ],
        "reship": [
            "classify_ticket", "fetch_order", "knowledge_lookup", "reship",
            "write_reply", "notify", "audit_log",
        ],
        "complaint": [
            "classify_ticket", "fetch_order", "escalate_to_human",
            "write_reply", "notify", "audit_log",
        ],
    }

    def plan(self, goal: str, skill_cards: list[dict], payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {c["name"] for c in skill_cards}
        text = payload.get("text", "")
        if any(k in text for k in ("破损", "少件", "补发", "换货")):
            branch = "reship"
        elif any(k in text for k in ("投诉", "态度", "升级", "人工")):
            branch = "complaint"
        else:
            branch = "refund"
        names = [n for n in self.DEFAULT_PLANS[branch] if n in allowed]
        return {
            "reasoning": (
                f"目标「{goal}」属于{branch}类售后任务：先取事实与画像，再做策略判定，"
                "随后执行有副作用的动作，最后输出与审计。辅助检索只在需要时插入，"
                "不作为答案来源。"
            ),
            "steps": [
                {"skill_name": n, "args": {}, "rationale": f"{branch} 链路第 {i + 1} 步"}
                for i, n in enumerate(names)
            ],
        }


class OpenAICompatLLM:
    """OpenAI 兼容 Chat Completions 实现；仅用标准库，避免额外依赖。"""

    SYSTEM = (
        "你是任务规划器。只依据给定的能力清单把用户目标拆成有序步骤，"
        "不要编造清单外的能力。仅输出 JSON："
        '{"reasoning": "简短说明", "steps": [{"skill_name": "...", "args": {}, "rationale": "..."}]}'
    )

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def plan(self, goal: str, skill_cards: list[dict], payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": self.SYSTEM},
                {"role": "user", "content": json.dumps(
                    {"goal": goal, "available_skills": skill_cards, "payload": payload},
                    ensure_ascii=False,
                )},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_fence(content))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("steps"), list):
            raise ValueError("LLM returned an invalid plan shape")
        return parsed


def build_llm(cfg: Settings = settings) -> LLMProvider:
    if cfg.llm_provider == "openai_compat" and cfg.llm_api_key:
        get_logger("der.llm").info("using OpenAI-compatible provider: %s", cfg.llm_model)
        return OpenAICompatLLM(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model)
    return MockLLM()
