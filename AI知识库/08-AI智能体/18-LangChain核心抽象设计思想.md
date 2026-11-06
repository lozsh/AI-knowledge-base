---
tags:
  - 智能体
  - 大模型
  - 提示词
  - RAG
  - 检索
---

# LangChain 核心抽象的设计思想

<p class="note-date">更新于 2026-11-03</p>
**一句话定义**：LangChain 沉淀的六个组件抽象——Model I/O、Retrieval、Chain、Memory、Agent、Callback——及其分界逻辑（链 = 硬编码序列，代理 = LLM 决策序列），比任何版本的具体 API 都耐用。

## 核心概念

**大模型应用开发的新范式（本文最重要的一个判断）**：操作的序列不再硬编码在代码中，而是**使用语言模型来选择执行的操作序列**。这是理解 Chain 与 Agent 分界、乃至整个 Agent 时代的钥匙。

**六大组件**（记忆框架，API 早已改版但分层思想未变）：
1. Model I/O：提示 → 模型 → 解析
2. Retrieval（含早期 Indexes）：文档加载/切分/嵌入/存储/检索
3. Chains：组件的编排
4. Memory：跨调用的状态
5. Agents：LLM 驱动的自主决策与工具调用
6. Callbacks：生命周期钩子/可观测性

## 关键方法/模式

### 1. Model I/O = Format + Predict + Parse

- **提示模板（Format）**：带占位符变量的模板对象，价值在于——一次定义多处复用、自动提取和校验变量、换模型不改提示代码、与输出解析器组合。类似 ML 框架里"模型可换、训练框架复用"的关系。
- **模型通用接口（Predict）**：文本模型（text→text）、聊天模型（消息列表→消息）、嵌入模型（text→向量）三类统一抽象，换后端零成本。
- **输出解析器（Parse）**：定义 ResponseSchema（字段+描述）→ 生成 format_instructions 注入提示 → 解析模型输出为结构化数据（字典/Pydantic）。
  - 关键设计：**把"预期输出格式"作为 prompt 的一部分注入，让生成端和解析端共享同一份契约**。

### 2. Chain：硬编码的操作序列

- LLMChain（提示+模型的最小组合）→ SequentialChain（顺序流水线，前段输出作后段输入）→ RouterChain（动态路由：一个 LLM 判断意图，把输入分发给多个目标链之一 + 默认链兜底）。
- RouterChain 是"链"里唯一的动态成分，也是走向 Agent 的过渡形态。

### 3. Memory：历史怎么进上下文的四种策略

原理全部相同：**把对话历史填进提示模板的 {history} 变量**，LLM 本身无状态。差异只在取舍：

| 机制 | 策略 | 优点 | 代价 |
|---|---|---|---|
| Buffer | 全量保存 | 信息最全 | token 线性增长，撞上下文上限 |
| Buffer Window | 只留最近 k 轮 | token 恒定 | 完全遗忘 k 轮之前 |
| Summary | LLM 滚动汇总 | 长对话省 token | 早期多花 token；细节丢失；依赖汇总模型能力 |
| Summary Buffer | 超过 max_token_limit 的旧内容做摘要，近期保留原文 | 兼顾远近（对应记忆的长期+短期） | 实现最复杂；短对话反而更贵 |

经验：单模型回答 + 另一个模型做汇总可以分离；客服类场景可叠加 RAG（短期全量 + 长期摘要 + 向量库辅助）。多用户并发时记忆必须按用户/会话隔离。

### 4. Agent 三要素 + AgentExecutor 运行时

- 三要素：**Agent 类**（LLM+提示驱动，决定下一步做什么）、**Tools**（工具函数 + 正确且清晰的描述）、**AgentExecutor**（运行时：调用代理、执行工具、处理异常）。
- Toolkits：面向一个目标的成组工具（如 Office365 收发件一组）。
- **工具的两条铁律**：不给正确的工具就完不成任务；描述写得不好就不知道怎么用——"如果你自己都说不清该用哪个工具，别指望模型选对"。

AgentExecutor 循环（`_take_next_step`，任何 Agent 运行时的原型）：
1. `agent.plan()`：拼提示（工具清单 + 格式指令 + 累积的思考轨迹）→ 调 LLM；
2. 解析输出为 AgentAction（工具+参数）或 AgentFinish（结束）；
3. 执行工具得到 Observation，追加进历史，回到 1；
4. 输出 AgentFinish 才退出循环。

**ReAct 提示词模板的解剖**（值得背下来的结构）：
```
Answer the following questions as best you can. You have access to the following tools:
<每个工具的名称+描述>
Use the following format:
Question: ... 
Thought: ...
Action: [工具名之一]
Action Input: ...
Observation: ...
(Thought/Action/Action Input/Observation 可重复 N 次)
Thought: I now know the final answer
Final Answer: ...
Begin!
Question: <任务>
<之前每一轮的 Thought/Action/Observation 完整累积>
```
要点：轨迹累积式提示（每轮重发全部历史）、以 "Final Answer" 作为终止信号、不同 AgentType 本质是不同模板。

### 5. Agent 类型族（按任务形态选）

| 类型 | 适用场景 | 机制要点 |
|---|---|---|
| Zero-shot ReAct | 通用单步循环 | 每轮只用一个工具，输入是字符串（刻意简化求稳） |
| Structured Chat | 多工具组合的复杂操作 | Action 输出为 JSON，可组合工具箱内多个工具 |
| Self-Ask with Search | **多跳问题**（答案依赖子问题的答案） | 自我追问 Follow-up Question + 搜索返回 Intermediate Answer，逐步逼近 |
| Plan-and-Execute | 长任务 | **规划与执行分离**：Planner LLM 先出计划，Executor LLM 按子任务调用工具；可换不同模型、可并行 |

Plan-and-Execute 的代价：计划时无环境反馈，一步错步步错，对模型稳定性要求高——这是后来 REWOO/LLMCompiler 等模式继续演进的起点。

### 6. Callback：可观测性钩子

- 在组件生命周期关键节点（LLM 开始/结束、工具开始/结束、链开始/结束）触发处理器，用于日志、监控、token 计数等。
- 这是后来 LangSmith/Tracing 类平台的原型思想：**Agent 调试必须靠事件级追踪，而不是 print**。

## 术语表

| 术语 | 含义 |
|---|---|
| Model I/O | 输入提示(FORMAT)、调用模型(PREDICT)、解析输出(PARSE)三环节统称 |
| format_instructions | 输出解析器生成的格式说明，注入 prompt 供模型遵循 |
| RouterChain | 用 LLM 判断意图并分发到子链的路由链 |
| AgentExecutor | Agent 的运行环境/引擎，驱动"计划→工具→观察"循环 |
| AgentFinish | 代理输出类型之一，表示任务完成、循环终止 |
| 多跳问题 (Multi-hop) | 答案需经多个中间问题/信息源组合才能得到的问题 |
| Self-Ask | 代理自我提出追问并用搜索获取中间答案的技巧 |

## 经验与常见坑

- **输出格式无保证**：即便注入了 format_instructions，模型也可能输出"看起来像 JSON 但少个逗号"的内容，或包一层代码围栏——解析器只是"尽力而为"，业务层必须做容错重试（可用 OutputFixingParser 思路：解析失败让 LLM 修复）。
- **Agent 输出同时包含最终答案和可解析动作**时解析器会抛异常——换不同厂商模型时常见，本质是模型对 ReAct 格式的遵循度不同；选模型要验证其工具调用稳定性。
- **温度与稳定性**：复杂多工具任务上 temperature 高会导致结果不稳定，"多跑几次才对"不是工程方案——调低温度或换模型。
- **token 复利**：ReAct 每轮都重发全部历史轨迹，长任务 token 消耗是平方级增长；Plan-and-Execute / REWOO 类模式部分是为省 token 而生。
- **异步不稳就先同步**：早期生态异步链路 bug 多，调试阶段用同步方式排除变量。
- 部署型工具箱（浏览器、Gmail 等）的工程成本在凭证配置和依赖安装，不在代码本身。

## ⚠️ 时效性说明

- 本文基于 2023 年的 LangChain（0.0.x~0.1.x），文中所有 API（`initialize_agent`、`LLMChain`、`ConversationChain`、各 Memory 类）**均已废弃**：现已被 LCEL 表达式（`prompt | model | parser`）、LangGraph（AgentExecutor 的继任者）和 `langchain_core.messages` 体系取代。
- 本文只收设计思想与模式；复现任何功能请查当前官方文档，不要照抄文中基于旧版 API 的示例。
- Zero-shot ReAct 文本模板已被原生 function calling / tool use 接口大幅替代，但"工具描述 + 格式契约 + 轨迹累积 + 终止信号"的骨架在新接口下依然成立。