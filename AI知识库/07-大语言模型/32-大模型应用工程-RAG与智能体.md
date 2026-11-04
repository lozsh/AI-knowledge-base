# 大模型应用工程：提示工程、RAG 与服务化

<p class="note-date">更新于 2026-11-03</p>
> 一句话概括：大模型落地应用的三大件——写好提示词、外挂知识库（RAG）、封装成对外服务，以及每个环节的选型与坑。

## 核心概念

### 为什么需要应用工程
大模型核心能力只有两样：**意图理解 + 文本生成**。其余短板（知识时效性、复杂任务执行、文件操作、企业系统集成）都靠应用层补——这正是 Agent 与 RAG 存在的理由。

### Agent 与工具化三级
- **Agent = LLM 为核心控制器的代理系统**：控制端（记忆/思考/决策）+ 感知模块 + 行动模块；经典三组件：**任务规划（Planning）、记忆（Memory）、工具（Tools）**。
- LLM 工具化三级：**使用工具**（插件/联网）→ **调用 API**（Function Calling）→ **制造工具**（Code Interpreter）。
- 经典规划方法 **ReAct**：Thought（思考）→ Act（执行动作）→ Obs（环境反馈）循环；CoT 负责任务分解。坑：ReAct 死循环需兜底。
- 记忆三层类比：感觉记忆 ≈ Embedding（高维表示）、短期记忆 ≈ Prompt（当前上下文）、长期记忆 ≈ 外部向量存储。

## 关键方法/原理

### 提示工程（Prompt Engineering）
- 本质认知：大模型交互是 **prompt/completion（提示/补全）**，不是 question/answer——输出是逐 token 按概率取最大的自回归补全。
- **好提示六模块**：任务（Task，动作动词开头）+ 上下文（Context）+ 示例（Examples）+ 角色（Persona）+ 格式（Format）+ 语气（Tone）。重要性：任务 > 上下文 > 其余；**必须含任务+上下文**，其余按需。
- 三个实用方法：一次性写全提示（省多轮轮次）；迭代式给步骤约束（"第一步…第二步…"显著提升代码生成质量）；**万能技巧：让模型当"提示工程师"为你迭代生成提示**（输出"修改后的提示+追问"循环）。
- 提示的角色分工：system / user / assistant；代码场景加 observation（外部工具返回，必须紧跟 assistant 之后）。system 与用户输入隔离，可控制行为并**缓解注入攻击**（类比 XSS，只能缓解不能杜绝）。

### RAG（检索增强生成）
两阶段流程：
1. **入库**：文档加载（PyPDF2/pdfplumber 抽文本，扫描件走 OCR）→ 切分（Recursive Character Text Splitter）→ Embedding 向量化 → 存向量库（Faiss/Milvus）；
2. **查询**：问题向量化 → 向量检索 → 检索片段拼进 prompt → LLM 作答。

- 相似度：余弦相似度 = 点积/(‖a‖·‖b‖)；Faiss `IndexFlatL2` 用欧氏距离且要求 float32，用余弦需先归一化向量。
- Embedding 模型选型：通用句向量用 bge 系列（如 bge-large-zh-v1.5）；词级用 Word2Vec/fastText。
- **核心优点**：知识准确（检索原文）+ 更新即时（无需重训重部署）。
- **选型口诀：能 RAG 就不微调**——知识问题交给 RAG，推理/逻辑/风格问题才微调。

### 本地部署与推理服务
- 企业两条路：MaaS 调 API（有数据安全问题）vs 开源模型私有化；常见**混合架构**。
- 部署锚点（6B 模型）：单张 RTX3090（24G）可微调+推理；FP16 约 13GB，INT4 约 6GB，CPU FP32 约 32GB 内存。
- 推理超参：max_length（输入+输出总上限）、temperature（越低越确定）、top_p（核采样）。
- **服务化分层模式**：Python 封装模型 API（内层，FastAPI + Uvicorn + Pydantic）+ Java/网关套壳对外（外层，鉴权/限流/熔断/降级/可观测）——模型服务独立部署与扩容，高内聚低耦合。
- **流式输出**：SSE（Server-Sent Events）逐 token 推送 `data: {...}`；模型用单例懒加载（ModelManager）。
- 生产四考量：推理效果、吞吐量、限流（保护 GPU 集群）、降级开关（服务不可用时隐藏 AI 功能而非硬报错）。
- 工程框架地图：LangChain（链式调度）+ LangSmith（观测/评测）+ LangServe（API 部署）+ LangGraph（有状态多角色）；Flowise 零代码可视化。**注意：LangChain/AutoGPT 是原型验证工具，不能直接上生产**。

## 术语表

| 术语 | 英文 | 含义 |
|---|---|---|
| 提示工程 | Prompt Engineering | 设计输入使模型输出符合预期的方法论 |
| 检索增强生成 | RAG（Retrieval-Augmented Generation） | 先检索知识再拼 prompt 生成，外挂开卷 |
| 词嵌入 | Embedding | 文本映射为语义向量 |
| 向量库 | Vector Store | Faiss/Milvus 等近似最近邻检索引擎 |
| 核采样 | Top-p Sampling | 按累积概率截断的采样策略 |
| 函数调用 | Function Calling | LLM 结构化输出以调用外部 API |
| SSE | Server-Sent Events | 服务端单向流式推送，逐 token 输出的载体 |
| 懒加载 | Lazy Loading | 首次请求才加载模型，缩短服务启动时间 |

## 经验与常见坑

1. **分词质量直接决定 RAG 召回准确性**（"维修服务"被拆成"服务"则召回失准）；文档切片会破坏语义，切片粒度要按语义边界；
2. **维度灾难**：向量维度升高后距离难以区分，最近邻搜索变慢——向量库选型要考虑量级与索引类型；
3. 检索只是"字面匹配的变种"，别把 Embedding 检索奉为圭臬，工业级要配重排与多路召回；
4. 不同模型对同一提示响应差异大，提示词要针对具体模型调试，不可跨模型复用；
5. system 提示防注入只能缓解不能杜绝，敏感操作要靠外层鉴权兜底；
6. token 计量计费：自建或三方 API 都要记录 tokens 对账，否则成本失控；
7. 机器学习全是概率（OCR、embedding、LLM 皆然），产品设计必须接受"不准确"，留人工编辑兜底；
8. 常见环境坑：CUDA 与 PyTorch 版本必须匹配；HF 下载不全用 ModelScope/Gitee 镜像；vLLM 仅支持 Linux。

## ⚠️ 时效性说明

- LangChain 生态组件迭代极快，API 以官方文档为准；文中组件名（ConversationChain 等）部分已废弃；
- ChatGLM3-6B、LocalAI、AutoGPT 为 2024 年前后代表工具，选型结论（分层模式、RAG 流程、限流降级）长期耐用。