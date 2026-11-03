# LLM 应用工程：链式调用、记忆、Agent 与函数调用

/> 来源：公开课程资料自学整理（整理于 2026-11-03）
> 一句话概括：从多步提示语到 LangChain 链式调用，再到 Memory、Agent 与 Function Calling——LLM 应用工程化的主线是"让模型只做它擅长的决策，其余交给确定性代码"。

## 核心概念

- **链式调用（Chain）**：把"LLM + 提示语模板"封装成 LLMChain，用 SequentialChain 串联，前一步的 output_key 自动注入后一步的模板占位符。多步提示语的工程化、模板化。
- **Memory（记忆）**：对话上下文的封装机制，解决 token 窗口有限与"记什么"的选择问题。
- **Agent（中介/特工）**：让 LLM 自主"做选择题"——选择用哪个工具、输入什么参数、何时停止。兼具代理（代用户办事）与自主行动两层含义。
- **ReAct**：Reasoning + Acting，模型按 Thought → Action → Action Input → Observation 循环推理并调用工具（源自 Google Brain 论文，与前端框架 React 无关）。
- **Tool**：封装函数 + 名称 + description 供 Agent 选择的对象；**description 是 AI 选工具的唯一依据**。
- **Function Calling**：把"AI 选函数"内置为 API 能力——传 tools 定义，模型返回 tool_calls（函数名 + JSON 参数），程序执行后把结果以 role=tool 消息回传，再拿最终回答。
- **数据飞轮**：用户使用行为即标注数据——好产品 → 更多数据 → 更好模型 → 更好产品的正循环。

## 关键方法/原理

### 1. Agent 的本质是提示工程
MRKL 模板要求模型输出固定格式（Thought/Action/Action Input/Observation），程序解析后执行工具、把 Observation 拼回 Prompt 再调模型，循环至 Final Answer。所谓"智能"，一半在模型，一半在解析与回填的确定性代码。
- 常用类型：zero-shot-react-description（单轮）、conversational-react-description（多轮 + Memory）。
- `max_iterations` 限制重试次数，失败转人工，防死循环。

### 2. Function Calling 三步模式
①定义 tools（name + description + JSON Schema 参数）→ ②模型返回 tool_calls → ③执行后以 `role:"tool"` 消息回传结果，再次请求得自然语言答案。一次可触发多个函数调用（如多商家比价）。它比纯提示语版 ReAct 更稳定，是现代 Agent API 的通用形态（各厂商均为类似设计）。

### 3. 记忆策略谱系
| 策略 | 机制 | 取舍 |
|---|---|---|
| BufferWindow | 滑窗保留最近 N 轮 | 精确但遗忘更早内容 |
| Summary | LLM 摘要全部历史 | 省 token 但最近轮次不精确 |
| SummaryBuffer | 摘要 + 近期原文 | 平衡之选 |
| **Entity** | 只提取订单号/邮箱等实体及关联上下文 | **最实用："只记有用的事"** |

### 4. 输出稳定性：JSON 模式
口语化 Prompt 会让 JSON 输出混入寒暄文字导致解析失败。解法：开启 JSON Mode（response_format=json_object）+ 在 Prompt 中给出期望 JSON 示例（顺带锁定字段命名风格 snake_case/camelCase）。

### 5. 确定性：temperature=0 也不可复现
需同时固定 seed + 全部参数 + 提示语，且厂商只承诺"尽可能一致"；用 system_fingerprint 判断调用配置是否漂移。

### 6. 微调 vs 提示工程 vs 外挂知识（RAG）
| 手段 | 适用 | 代价 |
|---|---|---|
| 提示工程 | 通用任务、快速验证 | 几乎为零，首选 |
| RAG（Embedding 检索注入） | 固定知识库问答、时效知识 | 检索链路建设，最省钱 |
| 微调 | 分类/意图识别/风格化输出、稳定格式 | 训练数据 + 数倍推理/训练成本，最后选 |

微调 = 用自己的 prompt/completion 对调整模型参数，知识 + 风格注入且保留基础能力，可增量继续微调；成本是基础模型的数倍到数十倍。

### 7. HuggingFace 三级用法
本地 Pipeline（model+task 即推理）→ 免费 Inference API（试用，注意冷加载 wait_for_model）→ Inference Endpoint（一键部署云 GPU，按时长计费、可暂停）。

## 经验与常见坑

- **LLM 算术不可信**：多位数乘法都会错。正确模式：让 LLM 生成代码 → 代码解释器执行，而不是让它心算。
- **能代码解决的别用 LLM**：格式转换、字符串处理用 UtilityChain/代码做；多次调 LLM 的 Memory 方案又慢又费钱。
- Tool 的 description 写不好，Agent 就选错工具或胡编参数；描述中要写清异常场景的处理预期（如"查不到时请用户确认订单号"），否则 Agent 会反复重试再从别处敷衍答案。
- Whisper 长音频：切片应在静音处切（精确按时间切会切断句子）；把上一片段转录的最后一句话作为下一片段的 Prompt 保持连贯。
- 模型/框架迭代极快：早期 Completions 接口与旧版 LangChain 写法均已大改——学机制，不背 API。

## 术语表

| 中文 | 英文 |
|---|---|
| 链式调用 | Chain / Sequential Chain |
| 智能体 | Agent |
| 函数调用 | Function Calling |
| JSON 输出模式 | JSON Mode |
| 随机种子 / 指纹 | seed / system_fingerprint |
| 对话记忆（缓存/摘要/实体） | Memory (Buffer / Summary / Entity) |
| 任务矩阵 | Task Matrix |
| 数据飞轮 | Data Flywheel |
| 代码解释器 | Code Interpreter / REPL |

## ⚠️ 时效性说明

- LangChain 早期 LLMChain/Agent API 已被大幅重构（现为 LangChain 1.x / LangGraph 体系）；OpenAI Completions 接口已废弃。文中模式（ReAct 循环、tools 定义、role=tool 回传）机制层面仍通用。
- 微调价格倍数、模型名为 2023 年快照。
