---
tags:
  - Spark
  - 大数据
  - 数据工程
---

# Spark 核心原理与心智模型：RDD、DAG、Shuffle 与内存

<p class="note-date">更新于 2026-11-03</p>
> 一句话概括：Spark 的一切性能行为都源自四个心智模型——RDD 抽象 + 延迟计算、以 Shuffle 为边界的 DAG/Stage 划分、Stage 内算子融合的"内存计算"、以及统一内存管理下执行/缓存的抢占规则。

## 核心概念

### RDD：分布式数据集的抽象
- RDD（弹性分布式数据集）是 Spark 对分布式数据实体的抽象，囊括内存中和磁盘中的所有分布式数据。4 大属性：
  - **partitions**：数据分片列表（并行度的基础）
  - **partitioner**：分片切割规则（决定是否触发 Shuffle）
  - **dependencies**：与父 RDD 的依赖关系（窄依赖/宽依赖）
  - **compute**：封装计算逻辑的转换函数
- **编程模型**：Transformations 算子描述数据形态转换，Actions 算子触发计算、收集结果或物化到磁盘。
- **延迟计算（Lazy Evaluation）**：Transformation 不立即执行，仅当 Action 被调用时整条转换链才付诸执行。好处是引擎能看到完整 DAG，从而做全局优化（流水线融合、Catalyst 改写）。

### DAG 与 Stage 划分
- DAG（有向无环图）：顶点是 RDD，边是 dependencies 构成的父子关系。开发者视角下，DAG 通过在分布式数据集上不断调用算子构建。
- **Stage 划分口诀：以 Actions 算子为起点，从后向前回溯 DAG，以 Shuffle（宽依赖）为边界划分 Stages**。
- 窄依赖 vs 宽依赖：父 RDD 每个分区最多被一个子 RDD 分区消费 = 窄依赖（map/filter/union/coalesce）；否则为宽依赖（groupByKey/reduceByKey/join/repartition/distinct）。窄依赖可流水线执行，宽依赖必须跨 Stage 数据分发。
- 从 DAG 到执行的 4 阶段：划分 Stages → 创建 Tasks/TaskSets → 按调度规则分发 → Executors 执行。

### 内存计算的两层含义（最易被误解）
1. **第一层：分布式数据缓存**——RDD/DataFrame cache 到内存。注意：只有被频繁访问（引用次数 > 1）的数据集才值得缓存；一次性访问的数据 cache 反而净亏。
2. **第二层：Stage 内的流水线式计算**——同一 Stage 内所有算子**融合为一个函数**，一次性作用在输入数据集上，中间结果不落内存。对比 MapReduce：MR 任意两步之间都以磁盘为媒介交换数据；Spark 的 Stage 内计算全程无中间物化。
- 推论：**Shuffle 是流水线融合的中断点**。消除 Shuffle 的收益不只是省网络/磁盘，更是让更多代码融合成一个函数。这是"能省则省、能拖则拖"原则的理论根基。

### 调度系统："数据不动代码动"
- 调度系统核心职责：把 DAG 转化为分布式任务，按资源可用性与调度规则依序分发给 Executors。
- **核心原则：数据呆在原地不动，把计算代码分发到离数据最近的执行器**（计算本地性：PROCESS_LOCAL > NODE_LOCAL > RACK_LOCAL > ANY），最大限度降低网络开销。

## 关键方法/原理

### Shuffle 工作机制（性能问题的总根源）
- **定义：集群范围内跨节点、跨进程的数据分发**。2.0 之后统一由 Sort Shuffle Manager 管理。
- **Map 阶段（Shuffle Write）4 步**：
  1. 逐条计算记录的目标分区（Key 哈希），填充内存数据结构——收集类用 PartitionedPairBuffer，聚合类用 PartitionedAppendOnlyMap（Value 可累加，溢写次数和中间文件都更小）
  2. 结构填满后，按（目标分区 ID，Key）排序，整体溢写到磁盘临时文件，清空结构
  3. 重复 1-2 直到分片处理完
  4. 对所有临时文件与内存残留做归并排序，生成最终中间文件：**data 文件（键值对数据）+ index 文件（各 Reduce 分区的偏移地址）**
- **Reduce 阶段（Shuffle Read）**：Reduce Task 依据 index 文件定位属于自己的数据段，从**所有** Map Task 的中间文件跨网络拉取。M 个 Map Task × N 个 Reduce Task = M×N 次数据交换，网络开销随两端并行度乘积爆炸。
- **Shuffle 为何是性能杀手**：CPU（哈希/排序）、内存（缓冲结构与读缓存）、磁盘（溢写与中间文件）、网络（全量分发）——四类资源通吃，且磁盘/网络延迟比 CPU/内存高几个数量级，天然无法均衡。

### 统一内存管理
- **堆内内存**：JVM 堆，由 GC 代理申请/释放。两个隐患：Spark 对可用内存的估算可能**高估**（释放有延迟，OOM 埋雷）；GC 频繁扫描回收本身损耗性能。
- **堆外内存**：经 Unsafe API 直接向操作系统申请/释放，无 GC 开销，用量可精确计算（`spark.memory.offHeap.enabled` / `spark.memory.offHeap.size`）。
- **四个内存区域**（Executor 视角）：
  - **Reserved Memory**：固定约 300MB，存 Spark 内部对象，动不得
  - **User Memory**：自定义数据结构（如 Driver 分发下来的字典），= (堆内存 − 300MB) × (1 − spark.memory.fraction)
  - **Execution Memory**：Shuffle/Sort/Aggregate 等执行用，= (堆内存 − 300MB) × fraction × (1 − storageFraction)
  - **Storage Memory**：RDD 缓存与广播变量，= (堆内存 − 300MB) × fraction × storageFraction
- **执行/缓存抢占 3 规则**（1.6+ 统一内存管理，边界是"虚线"）：
  1. 对方空闲时双方都可抢占
  2. **缓存抢占的执行内存，执行任务要用时必须立即归还**（缓存要么落盘要么清除）——因为缓存丢了可重算，执行任务被挂起则 CPU 空转
  3. **执行抢占的缓存内存，执行完才释放**——执行中的任务无法中断
- Catalyst 与 Tungsten（Spark SQL 两大引擎组件，见 13 篇 Join 调优与 14 篇生态）：
  - Catalyst 负责逻辑/物理计划优化（谓词下推、列剪枝、Join 策略选择）
  - Tungsten 负责执行层：UnsafeRow 二进制行格式取代 JVM 对象（省内存、减 GC），128 位内存页统一管理堆内外内存，**WSCG 全阶段代码生成**把 Stage 内算子编译成一个 Java 函数（消除虚函数调用、提升 CPU 缓存命中率）——这正是"内存计算第二层含义"的落地机制。

## 术语表

| 术语 | 含义 |
|---|---|
| RDD / DataFrame / Dataset | 分布式数据集三代抽象；DataFrame 带 Schema 可被 Catalyst 优化，RDD 是黑盒 |
| 窄依赖 / 宽依赖 | 分区一对一（或同源）映射 / 存在跨分区消费；宽依赖 = Shuffle = Stage 边界 |
| DAG / Stage / Task | 执行流程图 / 以 Shuffle 切分的执行阶段 / Stage 内单分片上的计算单元 |
| Shuffle Write / Read | Map 端落盘中间文件 / Reduce 端跨节点拉取 |
| data / index 文件 | Shuffle 中间文件的数据部分 / 各分区偏移量索引 |
| Execution / Storage / User Memory | 执行、缓存、用户自定义结构三类内存区域 |
| 堆内 / 堆外内存 | JVM 托管（有 GC、估算不精确）/ Unsafe 直管（精确、无 GC） |
| 本地性级别 | PROCESS_LOCAL > NODE_LOCAL > RACK_LOCAL > ANY，越靠后网络开销越大 |
| WSCG | Whole-Stage Code Generation，全阶段代码生成 |
| 谓词下推 / 列剪枝 | 过滤条件尽量贴近数据源执行 / 只扫描需要的列 |

## 经验与常见坑

- **逢 RDD 便 cache 是大忌**：cache 的收益前提是"引用次数 > 1 且重算成本高"；滥用后性能反而比不缓存差（见 12 篇调优方法论）。
- **聚合需求禁用收集类算子**：需要计数/求和时用 reduceByKey/aggregateByKey（Map 端预聚合），不要用 groupByKey/collect_list——前者溢写少、中间文件小，后者把原始数据全量分发，是调优大忌。
- 消除 Shuffle 的收益是双份的：既省四类硬件资源，又保住 Stage 内的算子融合。所以"把 Shuffle 往后拖"（先 map 端聚合/过滤再 Shuffle）有实际性能含义。
- 堆内内存的 OOM 常常不是"真的没有内存"，而是 Spark 高估了可用量；对稳定性敏感的场景可开启堆外内存。
- 理解内存区域归属才能定位问题：dict 这类 Driver 分发的自定义结构在 User Memory；cache 在 Storage；Shuffle 的 Buffer/HashMap 在 Execution。
- ⚠️ "内存计算 = 把数据放内存里所以快"是流行误解：内存计算的实质是**计算融合**（Stage 内无中间物化），缓存只是其中一层含义。

## ⚠️ 时效性说明

- 本文基于 Spark 3.0（2020 年前后）。RDD 仍是底层模型，但日常开发以 DataFrame/SQL 为主；RDD 算子（groupByKey 等）在新代码中已少用，原理性内容不受影响。
- Sort Shuffle Manager 的 bypass 机制（`spark.shuffle.sort.bypassMergeThreshold`，默认 200）在后续版本仍在；Shuffle 细节若读源码需以所用版本为准。
- 统一内存管理的区域公式自 1.6 起稳定；Reserved Memory 300MB 在 Spark 3.x 中仍保留。