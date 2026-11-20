# ADR 0002：按阶段加载上下文，替代一次性 RAG 塞入

- 状态：已接受
- 日期：2026-11-19

## 背景

「把相关文档一次性检索出来塞进 prompt」是问答系统的默认做法，但在数字员工场景里
有两个明显问题：任务有 5~8 步，第 1 步需要的政策和第 6 步需要的完全不同；
长上下文里混入无关片段会显著影响推理稳定性，且每一步都重复付费。

## 决策

- 知识切成 `ContextSlice`，登记 id、内容、token 估算、阶段标签。
- 每个 `SkillSpec` 用 `required_context` 声明本步骤需要的 slice id。
- `ProgressiveContextLoader.load_for(spec)` 只加载这些片，并受 `ContextBudget` 约束。
- 工具返回的完整数据不进入下一轮 prompt，只把摘要与 artifact 引用写回。
- 保留 `context/baseline.py` 的 Eager 实现，仅用于 `benchmarks/context_cost.py` 对照。

## 为什么不让 RAG 当核心

RAG 回答「这件事是什么」，数字员工要回答「这件事做完了没有」。
检索结果最多是某一步的输入，不能成为链路本身。因此 `knowledge_lookup`
被实现为一个可选、可被跳过的 Skill，而不是入口。

## 后果

- 正面：上下文开销随步骤数线性可控，且每一步的推理输入可复现、可审计。
- 代价：需要人工维护 slice 的 id 与阶段标签；切片命名不规范会导致漏加载。
  缓解手段是 `loader.load_for()` 对未知 id 直接抛 `ContextSliceNotFound`，不静默降级。
- 验证：`tests/test_progressive_context.py` 断言「只加载声明的片」「超预算被裁剪并有留痕」；
  `benchmarks/context_cost.py` 给出量化对比。
