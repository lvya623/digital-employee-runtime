# 架构设计

## 0. 一句话

把「用户的一句话任务」变成一条**可观测、可重试、可回滚**的执行链路：
`Task → Planning → ReACT → Tool/Skill 调用 → 输出`，而不是一次 RAG 问答。

## 1. 分层

```
┌──────────────────────────────────────────────┐
│ api/            FastAPI：协议转换、鉴权预留     │
├──────────────────────────────────────────────┤
│ runtime/        Planner / ReACT / Executor     │
│                 State / Memory / LLM Provider  │
├───────────────┬───────────────┬──────────────┤
│ skills/       │ context/      │ multi_agent/ │
│ Registry      │ Budget        │ Bus          │
│ Skill 实现     │ StageLoader   │ Coordinator  │
├───────────────┴───────────────┴──────────────┤
│ domain/      纯 dataclass：Task/Plan/Step/Event│
├──────────────────────────────────────────────┤
│ persistence/  SQLAlchemy：任务、轨迹、幂等键   │
└──────────────────────────────────────────────┘
```

依赖方向单向向下，`domain` 不依赖任何框架。这样 AI 生成的业务代码只能落在
`skills/builtin/`，改不坏编排层——这是「能管理大规模 AI 生成代码」的前提。

## 2. Agent / Skill / Memory 解耦

| 概念 | 归属 | 职责 | 不允许做 |
|---|---|---|---|
| Agent | `runtime/` | 决定**下一步做什么** | 不实现业务、不直接读库 |
| Skill | `skills/` | 决定**这件事怎么做** | 不读全量上下文、不持有状态机 |
| Memory | `runtime/memory.py` | 保存跨步骤 / 跨会话事实 | 不参与调度决策 |
| State | `runtime/state.py` | 执行链路的**当前位置** | 不存业务数据 |

`Memory` 与 `State` 分开是关键：State 是「我执行到第几步」，Memory 是「这个客户上周投诉过」。
混在一起会让回滚逻辑无法写正确。

## 3. Skills 体系

每个 Skill 用 `SkillSpec` 声明式描述自己：

```python
SkillSpec(
    name="refund",
    kind="api",
    required_context=("order", "policy.refund"),  # ← 只加载这两片
    produces=("refund.receipt",),
    retryable=True,
    compensatable=True,
    risk=RiskLevel.HIGH,
)
```

- `SkillRegistry` 负责注册、版本、依赖解析、健康检查和**给 Planner 的紧凑清单**
  （只暴露 name / kind / description / required_context，不暴露实现）。
- `describe_for_planner()` 也会被预算裁剪：Skill 多的时候按 tags 过滤，
  避免工具清单本身把上下文撑爆。
- `kind` 区分 API / Workflow / Tool：Workflow 是多个 Skill 的组合执行，
  由 `skills/loader.py` 做拓扑排序后串行/并行调度。

## 4. 渐进式上下文（Progressive Context）

传统做法：把客户资料 + 历史工单 + 知识库 + 政策一次性塞进 prompt。
问题：成本高、无关信息稀释推理、长上下文下稳定性下降。

本项目做法：

1. 所有知识先切成 `ContextSlice`，登记 id / token 估算 / 阶段标签。
2. 每个 Skill 在 `required_context` 里声明**它这一步需要哪几片**。
3. `ProgressiveContextLoader.load_for(spec)` 只取这些片，按 `ContextBudget` 裁剪；
   超预算时按 `compress()` 做摘要式截断，并留痕。
4. 工具返回的完整 Observation 落到 artifact 存储，只有摘要进入下一轮推理。
5. `benchmarks/context_cost.py` 用同一任务对比 Eager 与 Progressive 的 token 开销。

## 5. 执行链路与状态机

```
PENDING → PLANNING → RUNNING → SUCCEEDED
                       ├─→ NEEDS_HUMAN（高危动作等待确认）
                       ├─→ FAILED → ROLLED_BACK（逆序执行补偿）
                       └─→ FAILED（无补偿，保留现场待人工）
```

`Executor` 保证：

- **幂等**：每个 `(task_id, step_id)` 生成 `idempotency_key`，重复执行不产生第二次副作用。
- **重试**：仅 `RetryableError` 进入指数退避，上限可配；`NonRetryableError` 立即失败。
- **回滚**：有副作用的 Skill 返回 `compensation` 闭包并压栈；任一后续步骤失败时逆序执行。
- **轨迹**：每个状态变化、每次工具调用、每次补偿都写 `Event`，`GET /tasks/{id}/trace` 可回放。

## 6. Multi-Agent

`Coordinator` 只在任务被判定为复杂（跨领域 / 步骤数超阈值）时启用：
把子任务发给独立 `Worker`，每个 Worker 有隔离的 `ProgressiveContextLoader` 与状态，
通过 `InMemoryBus` 回传结果；某个 Worker 失败不阻塞其他分支，最终由 Coordinator 聚合或降级。

刻意保持轻量：不做常驻网关、不做角色扮演式对话，避免为了「多智能体」而引入不确定性。

## 7. RAG 的定位

`knowledge_lookup` 是一个**可选** Skill，只在分类不确定时被调用，且返回值只是给后续
Skill 的一片上下文，不直接生成答案。GraphRAG 预留了 `ContextSlice.graph` 元数据字段，
当前未启用。核心链路始终是执行，不是检索。

## 8. 可观测性

结构化 JSON 日志统一带 `task_id` / `step_id` / `skill` / `attempt`；
`Event` 轨迹落库，可用于回放、审计与回归用例构造。这是把 AI coding agent
当作协作开发者之后，人能真正 review 系统的前提。
