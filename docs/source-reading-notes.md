# 源码研读笔记：Claude Code Harness 与 Hermes Agent

> 目的：不是复述 README，而是回答「这两个项目解决了什么问题、我借鉴了什么、我为什么没照抄」。
> 读的是架构，不是抄代码。

## 一、Claude Code / Claw Code（Agent Harness 视角）

- 参考：`https://github.com/instructkr/claw-code`（Python/Rust 的 clean-room 重实现，
  用来理解 harness 结构而非使用泄露源码）；官方 `anthropics/claude-code` 为闭源 CLI。
- Harness 的关键不在模型，而在**外壳**：命令系统、工具集成、子系统清单、
  工作空间清单、以及一个稳定的 `观察 → 决策 → 工具调用 → 再观察` 循环。
- 值得借鉴的三点：
  1. **模型与外壳解耦**：换模型不动执行链路。本项目对应 `runtime/llm.py` 的
     `LLMProvider` 协议 + `MockLLM` / `OpenAICompatLLM` 双实现。
  2. **工具是一等公民**：工具有注册表、有元信息、有可发现性。对应 `skills/registry.py`。
  3. **工作空间快照**：变更前后的状态可比对。对应执行链路的 `compensations` 栈与事件轨迹。
- 我没照抄的部分：终端交互式 TUI、文件编辑类工具集。本项目面向服务端批处理工单，
  需要可审计、可回滚、可并发，不是单机编码助手。

## 二、Hermes Agent（NousResearch/hermes-agent，MIT）

- 参考：`https://github.com/NousResearch/hermes-agent`，
  文档 `https://hermes-agent.nousresearch.com/docs`。
- 它解决的核心痛点是「Agent 每次会话从零开始、用完即忘」，做法是
  **自进化学习闭环**：任务完成后自主沉淀 `SKILL.md`（兼容 agentskills.io），
  使用中改进技能；用 SQLite + FTS5 做跨会话召回；用 `delegate_tool`
  隔离子会话跑子代理；单进程网关接 15+ 消息平台。
- 拆开看，可复用的工程件是：
  - `run_agent.py` 的 `AIAgent` 对话环 + `Prompt Builder` / `Provider Resolution`；
  - `model_tools.py` + `tools/registry.py` 的 Tool Dispatch 与 toolset 开关；
  - `hermes_state.py` 的会话/记忆持久化分层；
  - 子代理隔离：独立上下文、独立终端、结果回收。
- 对应到本项目：`runtime/react.py` 的循环、`skills/registry.py` 的注册表 + 按需暴露给
  Planner 的紧凑清单、`runtime/memory.py` 的 Working / Long-term 分层、
  `multi_agent/worker.py` 的隔离 Worker。

## 三、我做的取舍（面试最该讲的一段）

| 议题 | Hermes / Claude Code 的做法 | 本项目的选择 | 原因 |
|---|---|---|---|
| Skill 从哪来 | 运行时自主创建并改进 | 人工评审后注册进 Registry | 企业售后场景涉及退款，技能必须可审计、可复现 |
| 上下文 | 长期记忆 + 跨会话召回 | 按阶段声明式加载 + 预算控制 | 目标是**推理稳定性与成本**，不是记得多 |
| RAG | 常作为知识主链路 | 降为可选辅助 Skill | 数字员工的任务是执行，不是问答 |
| 运行形态 | 常驻网关 / 多平台 | FastAPI + 可水平扩展的无状态编排 | 便于对接已有 Java/Python 业务系统 |

一句话总结：**从 Claude Code 学「外壳」，从 Hermes 学「Skill 与记忆的分层」，
但把「自进化」换成了「可审计」，因为数字员工要在真实业务里对钱和操作负责。**

## 四、还没吃透、准备继续读的点

- Hermes 的 `execute_code` 程序化工具调用如何压缩多步管线，能否迁移到 Skill 组合执行。
- FTS5 + LLM 摘要的召回质量评估方式，本项目长期记忆目前只做了接口层。
- Claw Code 从 Python 转向 Rust 后对工具循环延迟的影响，暂无实测数据。
