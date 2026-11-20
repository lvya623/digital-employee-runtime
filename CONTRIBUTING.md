# 贡献指南

## 开发约定

- Python >= 3.10，`pip install -e ".[dev]"`。
- 提交前必须 `pytest -q` 全绿；新增模块需带测试。
- 架构决策写进 `docs/adr/`，不要在代码注释里偷偷改设计。
- 与 AI coding agent 协作时遵守 `CLAUDE.md`：先读契约、再生成、后评审。

## 分支与提交

- `main` 保持可运行，功能在 `feat/*` 分支开发。
- Conventional Commits，一次提交一个问题。
- PR 描述里写清楚：改了什么、为什么、如何验证、AI 生成比例与人工改动点。

## 测试分层

| 层 | 测什么 | 位置 |
|---|---|---|
| 单元 | Registry 拓扑、上下文预算、状态机转移 | `tests/test_registry.py` 等 |
| 集成 | 执行链路的回滚 / 重试 / 幂等 | `tests/test_executor_rollback.py` |
| 协议 | FastAPI 任务提交与轨迹查询 | `tests/test_api.py` |
| 度量 | Progressive vs Eager 的上下文开销 | `benchmarks/context_cost.py` |

## 明确不做的事

- 不把 RAG 当核心链路；`knowledge_lookup` 只是可选辅助 Skill。
- 不在运行时让模型改写已入库的 Skill（企业场景需要可审计与确定性）。
- 不引入需要外部 API Key 才能跑通的核心测试；默认使用 `MockLLM`。
