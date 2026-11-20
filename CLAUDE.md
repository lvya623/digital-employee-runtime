# CLAUDE.md — 给 AI Coding Agent 的仓库协作手册

> 本仓库把 AI coding agent 当作**协作开发者**，不是黑盒生成器。
> 你可以写代码，但必须先理解契约、再给方案、最后接受 diff 评审与测试约束。

## 1. 先用 3 分钟读懂仓库

- `docs/architecture.md`：分层、状态机、执行链路的**唯一事实来源**。
- `src/der/domain/models.py`：所有跨层传递的数据结构。
- `src/der/skills/base.py`：`Skill` 契约（`SkillSpec` / `SkillContext` / `SkillResult`）。
- `docs/adr/`：已经拍板的设计决策，不要绕过它们重新发明。

## 2. 分层红线（违反即拒绝合入）

```
api  →  runtime  →  skills / context / multi_agent  →  domain
                          ↓
                     persistence
```

- `domain/` 是纯数据层：**禁止** import fastapi / sqlalchemy / 任何 IO。
- `skills/` 只依赖 `domain` + `context` 传入的切片，**禁止**自己读数据库或读全量上下文。
- `runtime/` 负责编排，**禁止**在 runtime 里写具体业务逻辑（业务一律落在 Skill）。
- `api/` 只做协议转换，**禁止**承载状态机。
- 跨层只能传 `domain` 里的 dataclass，不传裸 dict 作为业务语义载体。

## 3. 生成一个新 Skill 的标准流程

1. 写 `SkillSpec`，明确 `kind` (api/workflow/tool)、`required_context`、`produces`、
   `retryable`、`compensatable`、`risk`。
2. 实现 `BaseSkill.run(ctx)`，返回值必须是 `SkillResult`，不要抛裸异常。
3. 可重试失败抛 `RetryableError`；确定性失败抛 `NonRetryableError`。
4. 有副作用的 Skill 必须返回 `compensation` 闭包，并保证**幂等**（用 `ctx.idempotency_key`）。
5. 在 `registry` 注册，补一个单元测试：成功路径 + 失败回滚路径。
6. 跑 `pytest -q`，全绿才提交。

## 4. 生成代码的验收清单（人审 diff 时逐条过）

- [ ] 每个公开函数有类型注解与一句 docstring
- [ ] 异常被归类（可重试 / 不可重试 / 需人工），没有被 `except Exception: pass` 吞掉
- [ ] 关键路径有结构化日志（带 `task_id` / `step_id`）
- [ ] 外部调用有超时、重试上限、幂等键
- [ ] 新逻辑有测试，且测试断言的是行为而非实现细节
- [ ] 没有把大段文本一次性塞进 prompt（走 `ProgressiveContextLoader`）
- [ ] 没有新增 requirements 之外的第三方依赖

## 5. 禁止 AI 直接修改

- `docs/adr/*`（决策记录只能由人新增）
- `src/der/domain/models.py` 的字段语义（改名需人审）
- `LICENSE`、CI 的测试命令
- 任何 `risk=HIGH` 的 Skill 实现（可生成草稿，必须人审后合入）

## 6. 常用命令

```bash
pip install -e ".[dev]"
pytest -q
python scripts/demo.py
python benchmarks/context_cost.py
docker compose up --build
```

## 7. 提交规范

`feat(skills): ...` / `fix(executor): ...` / `refactor(context): ...` / `docs(adr): ...`

一次提交只解决一个问题；由 AI 生成的模块在 commit message 正文注明 `Co-authored-by: AI`，
便于后续按来源做代码审计与重构。**注释来源不等于放弃责任**：合入者仍需逐行读懂。
