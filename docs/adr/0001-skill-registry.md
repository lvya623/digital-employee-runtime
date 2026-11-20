# ADR 0001：用声明式 Skill Registry 替代硬编码调用链

- 状态：已接受
- 日期：2026-11-19

## 背景

数字员工要对接的业务能力会持续增加（查订单、退款、补发、升级人工、发通知……）。
如果把调用写成 `if ticket.type == ...: refund()` 这样的分支，新增能力要改编排层，
且无法在运行时向 Planner 说明「现在有哪些能力」。

## 决策

引入 `SkillSpec` + `SkillRegistry`：

- 能力以声明式元信息注册：name / kind / version / required_context / produces /
  retryable / compensatable / risk / depends_on / tags。
- 编排层只通过 `registry.get(name)` 取实现，不 import 具体业务模块。
- 组合执行由 `skills/loader.py` 按 `depends_on` 拓扑排序完成。
- Planner 只看 `describe_for_planner()` 的紧凑清单，且清单本身受上下文预算约束。

## 备选方案

| 方案 | 否决原因 |
|---|---|
| 函数调用硬编码 | 新增能力必须改编排层，AI 生成的代码会扩散到核心链路 |
| 直接用 LangChain Tool 列表 | 缺少 risk / compensatable / required_context 等企业执行所需元信息 |
| 运行时让模型自己写 Skill | 涉及资金操作，需人工评审入库（见 source-reading-notes.md） |

## 后果

- 正面：新增 Skill 只改 `skills/builtin/` + 注册 + 测试，编排层零改动；
  业务代码被物理隔离，便于 AI 批量生成与人工评审。
- 代价：多一层间接调用；`SkillSpec` 字段变更需要人审（已写入 CLAUDE.md 红线）。
- 验证：`tests/test_registry.py` 覆盖注册去重、依赖拓扑、环检测、清单裁剪。
