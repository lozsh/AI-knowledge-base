# 早期 Agent 框架的架构启示（MetaGPT / AutoGPT / Swarm / DSPy / BabyAGI）

/> 来源：公开课程资料自学整理（整理于 2026-11-03）
> 一句话概括：第一代 Agent 框架各有截然不同的核心抽象——SOP 角色扮演（MetaGPT）、服务化工作流（AutoGPT）、移交原语（Swarm）、提示词编译（DSPy）、任务三代理循环（BabyAGI）——这些抽象本身比框架更耐用。

## 核心概念

**MetaGPT 的两个公式**（可作为理解所有多智能体系统的基座）：
- 智能体 = LLM + 观察 + 思考 + 行动 + 记忆
- 多智能体 = 智能体 + 环境 + 标准流程（SOP）+ 通信 + 经济

**框架形态的两种根本路线**：
- MetaGPT：首先设计为**库**（library），装进你的 Python 进程。
- AutoGPT：首先设计为**在线服务**（B/S 架构，Server + Frontend 分离，RESTful API 交互），功能强但部署复杂度数量级上升。
- 选型含义：库形态适合嵌入应用，服务形态适合平台化/图形化编排/高可用场景。

## 关键方法/模式

### MetaGPT：SOP 驱动的角色扮演（Role-Playing）

- 三层抽象：**Team（雇佣多个 Role）→ Role（执行多个 Action）→ Action（具体行动，可调工具）**。
- 一个 Agent ≈ 一个岗位（产品经理/程序员/测试员），各司其职，输出物像流水线一样传递——SOP（标准操作流程）是多智能体协作的核心粘合剂。
- **事件驱动协作**：每个 Role 注册自己可执行的 Action、订阅（watch）自己感兴趣的 Action；上游 Action 的输出累积为下游 Action 的输入 context。串行/并行组合即构成工作流。
- **人类可以顶替任何一个 Role**（传入 is_human 参数）：100% 自动化难以实现时，人担任关键决策角色，"半自动化工作流"同样有价值。
- Role 与 LLM 的交互模式默认 ReAct，可切换为 Plan-and-Act。

### AutoGPT Platform：Agent ⊃ Workflow ⊃ Block

- 组件三层次：**Agent 基于（包含）Workflow，Workflow 基于（包含）Block**；Block 代表一次行动（Action），对应 MetaGPT 的 Action；Agent 对应 Role。
- Agent 不必只做 AI 任务：数据处理、任务调度、通知、系统集成都是合法的 Agent——"智能体本质是自动化工作流，AI 只是其中一类构建块"。
- Block 是可复用构建块（连接外部服务、数据处理、模型调用、条件逻辑），官方认证 + 自定义扩展都容易。
- 每个Agent 运行即一个 DAG 图执行，通过 graph_id 标识，异步执行 + 轮询取结果（保证服务可伸缩性）。

### Swarm：移交（Handoff）原语

OpenAI 开源的极简多智能体框架，核心只有两个概念：

- **Agent = 一组指令（instructions）+ 一组函数（functions）**。指令直接成为系统提示词；切换 Agent 时系统提示变、聊天记录不变。
- **Handoff：函数返回另一个 Agent 即完成执行权移交**——多智能体路由被压缩成一个函数返回值。
- `run()` 循环是全部核心：调 LLM → 有 tool_calls 则执行工具并追加到历史 → 必要时切换 Agent / 更新上下文变量 → 无 tool_calls 则返回。调用间不保存状态（无状态设计）。
- Python 函数自动转 JSON Schema 传给模型：docstring → 工具描述，无默认值参数 → required，类型提示 → 参数类型。函数出错时错误信息附进聊天，让 Agent 优雅恢复。
- 设计哲学：Agent 这个原语可以统一表示 agents / workflows / tasks——一个"由指令和函数定义的工作流或步骤"也是 Agent。
- 底座是 Assistants API（赋予 LLM 调外部工具的能力："不奢望 LLM 自己搞定一切"）。

### DSPy：把提示工程变成机器学习问题

针对的根本问题：提示词对模型极其敏感，换模型/换指标/改管道都要手工修补提示词——不可持续、无法快速迭代。

- 核心思路：**开发者写组合式 Python 代码（声明式签名），用优化器自动编译出高质量提示词/微调权重**，而非手写脆弱提示词。
- **Signature（签名）**：模块输入/输出行为的声明性规范，如 `"question -> answer: float"`——告诉 LM 做什么，不指定怎么做。
- **Module（模块）**：每个内置模块抽象一种提示词技术（`dspy.Predict`、`dspy.ChainOfThought`、`dspy.ReAct`），经泛化可处理任意签名；有可学习参数；可直接借鉴 PyTorch 的 nn.Module 心智模型组合成大程序。
- **Optimizer（优化器，前身 teleprompter）**：输入三样东西——你的程序、度量指标（metric 函数）、少量训练样例（5~10 个即可、可无标注）——自动调优提示词或权重。选型经验：10 个左右样例用 BootstrapFewShot；50+ 用 BootstrapFewShotWithRandomSearch；只优化指令用 MIPROv2（0-shot）；已有大模型且要高效程序用 BootstrapFinetune 微调小模型。
- 开发三阶段循环：**编程**（定任务、定初始管道）→ **评估**（收集开发集 + 定义 metric + 评估）→ **优化**（跑优化器），不满意回到编程，渐进迭代。
- 定位：DSPy 是机器学习框架，可嵌入任何 ChatBot/Agent 框架；手工提示词在简单场景仍有用，但不应把赌注全押在手工路线上。

### BabyAGI：任务三代理循环（目标驱动自主任务系统）

给一个目标后无限循环的三个代理（全部由 LLM 扮演）：
1. **执行代理** execution_agent：(目标, 任务) → 任务结果字符串。
2. **任务创建代理** task_creation_agent：(目标, 上一任务结果, 任务描述, 当前任务列表) → 新任务列表——**根据执行结果动态生成后续任务**。
3. **优先级代理** prioritization_agent：对任务列表重新排序。

结果存入向量库（Pinecone 等）为后续任务提供上下文。这是"目标 → 任务队列 → 执行 → 派生新任务"的经典自主循环。

### HuggingGPT：LLM 作控制器的四阶段

任务规划（解析请求生成任务列表及依赖）→ 模型选择（按专家模型描述分配）→ 任务执行（调用专家模型）→ 响应生成（整合结果）。体现"LLM 当大脑、专家模型当四肢"的路由思想。

## 术语表

| 术语 | 含义 |
|---|---|
| SOP | 标准操作流程，MetaGPT 中多 Agent 协作的流程规范 |
| Inception Prompting | CAMEL 的引导性提示（见已有笔记 11-框架开发实践） |
| Handoff | Swarm 中通过函数返回值把对话执行权移交给另一个 Agent |
| Signature | DSPy 中模块输入/输出行为的声明式规范 |
| Optimizer / teleprompter | DSPy 中自动调优提示词/权重的算法 |
| Bootstrap | DSPy 中让程序自己生成少样本示例再做筛选的优化策略 |

## 经验与常见坑

- 中文教程/翻译文档普遍滞后于快速演进的框架（AutoGPT 新旧版本完全不兼容），**学新框架直接读英文官方文档**，用翻译插件辅助。
- 独立部署型框架（AutoGPT Platform 类）依赖链很长（数据库、缓存、Docker），评估框架时要把**部署成本**算进选型。
- 轻量级框架 ≠ 玩具：Swarm 几百行代码固化了一组多 Agent 编排最佳实践；资深工程师应警惕 Design by Buzzwords、以复杂为荣的倾向，围绕解决业务痛点选型。
- 自主循环系统（AutoGPT/BabyAGI 类）的已知顽疾：**分心、陷入循环、成本失控、缺长期记忆**——任何"目标驱动无限循环"的设计都要配终止条件、预算上限和记忆机制（这一课在上下文工程笔记 19 中有系统解法）。
- MetaGPT 的 Role watch 机制提示：多智能体协作可以用"发布/订阅 + 事件"实现，不必点对点硬编码调用关系——解耦且易扩展。

## ⚠️ 时效性说明

- Swarm 已被 OpenAI 官方标记为实验性项目并由 Agents SDK 接续；AutoGPT/MetaGPT/DSPy API 均大幅演进。本文只提炼架构抽象（SOP/Block/Handoff/Signature/优化器/任务循环），具体类名和版本号不要照用。
- Assistants API 是 OpenAI 已宣布计划弃用的旧接口，理解其"工具外挂"思想即可，勿再基于它做新设计。
