---
tags:
  - Spark
  - 大数据
  - 数据工程
---

# Spark 性能调优方法论：瓶颈定位、资源分配与开发原则

<p class="note-date">更新于 2026-11-03</p>
> 一句话概括：调优的本质是木桶理论——只修最短的板；方法论是"定位瓶颈 → 从应用代码与 Spark 配置两层出手 → 随短板此消彼长动态切换 → 收敛于硬件资源均衡无瓶颈"。

## 核心概念

### 性能调优的本质（4 条）
1. 调优不是一锤子买卖：补齐一个短板，其他板子可能成为新短板，是动态持续的过程。
2. 手段是否高效取决于针对的是短板还是长板：**针对瓶颈事半功倍，针对长板事倍功半**。
3. 方法没有一定之规，随短板此消彼长动态切换。同一种调优手法"你那儿好使、我这儿不好使"，通常是因为它没触达你的瓶颈——别人的最佳实践不空谈，只是不适用于你的木桶。
4. 调优收敛于所有木板齐平、**各硬件资源（CPU/内存/磁盘/网络）运行时均衡、无瓶颈**的状态。实证：同样任务里跑得最快的配置不是 CPU 压满或内存拉满的，而是资源配置最均衡的。

### 典型反例：为什么"UDF 换 SQL functions"常常没用
- UDF 对 Catalyst 是黑盒，无法被优化，单点性能确实差（经验值慢 3%-5%）；但若端到端瓶颈在 Shuffle 或数据扫描，改写 UDF 对整体几乎无感。
- 教训：**任何"教科书建议"都要先问它针对的是不是你当前那块最短的板**。

### 定位瓶颈的两条途径
- **先验的专家经验**：开发/Code Review 阶段凭经验预判（老中医望闻问切）。
- **后验的运行时诊断**：Spark UI（Stage 耗时分布、Task 倾斜、GC 时间、缓存占用、Shuffle 读写量）+ 系统级监控（top/vmstat/iostat/iftop、Prometheus+Grafana）+ GC 日志分析（西医仪器）。
- 切入维度：先判断负载类型（计算密集/内存密集/IO 密集）缩小范围；再盯典型场景——**Shuffle 和数据关联对四类资源要求都高，是天然的瓶颈高发区**。

## 关键方法/原理

### 调优的两个层面
- **应用代码层面**：捕捉和移除性能 BUG——遵循"能省则省（避免 Shuffle）、能拖则拖（先过滤/预聚合再 Shuffle）"、避免单机思维、用内置函数替代 UDF（但先确认瓶颈）。
- **Spark 配置层面**：官网近百个配置项中，真正显著影响性能的屈指可数。围绕 Executors 划分三类：硬件资源类、Shuffle 类、Spark SQL 类。Driver 端只管调度，调优空间有限。

### 内存规划两步走（调内存配置的公式化方法）
第一步，预估三类区域的内存消耗（#E 为 Executor 数，#N 为线程池大小，#threads 为并发任务数）：
- User Memory：`#User = #size × #N`（自定义数据结构 × 每线程一份）
- Storage Memory：`#Storage = (#bc + #cache) / #E`（广播 + 缓存，按 Executor 均摊）
- Execution Memory：`#Execution = #threads × #dataset / #N`

第二步，反推配置项：
- `spark.memory.fraction = (#Storage + #Execution) / (三者总和)`
- `spark.memory.storageFraction ≈ #Storage / (#Storage + #Execution)`
- `spark.executor.memory = 300MB + #User + #Storage + #Execution`
- 目的：让各内存区域占比与实际数据消耗类型一致，内存利用率最大化。

### 并行度与 CPU 利用率（三足鼎立：并行度、并发度、执行内存）
- Executor 内每个 CPU 线程可申请的执行内存有上下限：**最高 1/N，最低 1/(2N)**（N = 线程池大小）。
- 数据分片过大 → 内存不足 → 线程挂起 → CPU 空转；分片过小 → 调度开销占主导。**最佳并行度 P：让平均分片大小 D/P 落在 (M/(2N), M/N) 区间**（M = 执行内存）。
- 经验锚点：**单个 Task 处理的数据分片以 200MB 左右为宜**；`spark.sql.shuffle.partitions` 默认 200，大表作业常需按"总量 / 200MB"重新估算。
- 缓存侧：`spark.rdd.compress` 开启压缩可大幅提升缓存存储效率（默认不压缩）。

### Cache 的正确用法
- 默认存储级别：RDD → `MEMORY_ONLY`；DataFrame → `MEMORY_AND_DISK`。
- 缓存 3 步：Unroll（Iterator 物化为对象）→ Transfer（封装 MemoryEntry）→ 注册（BlockId-MemoryEntry 进 LinkedHashMap）。
- 空间不足时的清除原则：**LRU**（最近最少访问优先逐出）+ **兔子不吃窝边草**（同一 RDD 的其他块有"赦免权"）。
- 使用 3 原则：
  1. 引用次数为 1 的数据集坚决不 cache
  2. 引用 > 1 且重算运行成本占比超约 30% 才考虑 cache
  3. cache 是惰性的，需接 `count()` 完全物化；且把待缓存数据赋给变量，后续操作基于该变量才能复用缓存。

### OOM 定位（两步法）
1. Stack Trace 定位代码位置；2. 区分 Driver 端还是 Executor 端、哪个内存区域。
- **Driver 端 OOM**：创建的数据集过大，或 collect 的结果集超上限 → 预估结果集尺寸、加大 Driver 内存，必要时避免 collect。
- **Executor 端 User Memory OOM**：与 Driver 同理（自定义结构过大）。
- **Executor 端 Execution Memory OOM**：数据分布与内存规划不匹配（任务内存请求超 1/N 上限），三条出路：消除倾斜 / 打散数据提高并行度降低粒度 / 加内存并同步调线程池。

### 磁盘与网络的视角
- 磁盘三大功能：溢写临时文件、缓存数据集、存 Shuffle 中间文件——是稳定性的底盘。**磁盘复用**（Shuffle 中间文件被重复利用）两用途：失败重试缩短重算路径；**ReuseExchange**——相同分区规则 + 相同字段的多个查询共享同一份 Shuffle 结果，只扫一次文件、只 Shuffle 一次。
- 网络三大削减点：读取阶段争取 `NODE_LOCAL` 本地性（计算与存储物理耦合）；处理阶段用 Broadcast Join 消 Shuffle、用 Map 端聚合减少分发量；分发前用 **Kryo 序列化**（需注册自定义类型，否则可能适得其反）。

## 术语表

| 术语 | 含义 |
|---|---|
| 木桶理论 | 端到端性能由最短板（瓶颈）决定，调优即不断补短板 |
| 并行度（Parallelism） | 数据分片数，决定 Task 数量 |
| 并发度 | 同时运行的 Task 数（#cores） |
| 1/N 规则 | 每线程执行内存上限 1/N、下限 1/(2N) |
| ReuseExchange | 物理计划相同 Shuffle 子树的中间结果复用 |
| Kryo Serializer | 高效 Java 序列化库，需注册类以获得最佳效果 |
| noop（Spark 3.0） | 只走流程不落盘/不计输出的基准测试模式，可测纯计算成本 |
| GC Log | GC 日志，导入 JVM 可视化工具分析频率与幅度 |

## 经验与常见坑

- 网上抄参数怼上去看时长变没变，是"调优"最常见的误区：不定位瓶颈的调参是撞运气。
- `spark.sql.shuffle.partitions` 一把梭设很大不一定好：分区过碎时调度开销与小文件问题吃掉收益。
- DataFrame 阈值判断的坑：Spark 判断"小表"依据的是磁盘上的统计尺寸，Parquet 压缩率高时，内存中展开的实际尺寸可能远超广播阈值，广播后 Driver OOM——判断前先 cache 再看执行计划里的统计值。
- 加内存不加并行度（或反之）都无效：并行度、并发度、执行内存三者必须联动调整（三足鼎立）。
- 调优前先跑基线、改一个变量、对比 Spark UI：多变量同时动无法归因。
- 收敛判断要量化：运行时长 + 稳定性 + CPU/内存/IO 利用率曲线是否彼此均衡。

## ⚠️ 时效性说明

- `spark.yarn.executor.memoryOverhead` 在 Spark 3.x 更名为 `spark.executor.memoryOverhead`（且不再需要把 offHeap.size 加进去，3.0+ 由 Yarn 自动计入）。
- Dynamic Allocation、AQE 开启后 `spark.sql.shuffle.partitions` 的影响被削弱（AQE 会自动合并分区），但初始值仍决定 Map 端输出分区数。
- 本文以 YARN 部署为背景；Kubernetes 部署下 overhead/本地性细节略有差异。