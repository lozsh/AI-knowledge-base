# Spark 生态与流计算：Spark SQL 实践模式与 Structured Streaming

<p class="note-date">更新于 2026-11-03</p>
> 一句话概括：Spark SQL 让批处理复用 Catalyst/Tungsten 引擎（数据格式、分区设计与查询模式决定性能上限）；Structured Streaming 用"无界表 + 微批"把流计算统一到 DataFrame/SQL 之上，Window 与 Watermark 是其两大核心机制。

## 核心概念

### Spark SQL 实践模式
- **数据源与格式**：DataFrame 从各类数据源读取（Parquet/ORC/CSV/JDBC/Hive 表）。列式存储 + 内置统计信息（min/max/null 计数等注脚）是谓词下推与列剪枝的前提——**生产首选 Parquet/ORC，CSV/JSON 只适合小数据或边界交换**。
- **性能优化三板斧（引擎自动做，但开发者要设计得让它们有得可做）**：
  1. **谓词下推**：过滤条件尽量贴近数据源执行，靠文件注脚统计信息跳过整块数据；效果受文件内容"纯度"限制。
  2. **列剪枝**：只扫描查询需要的列，列式存储下收益巨大——所以"select * 抄全表字段"是反模式。
  3. **分区剪裁**：分区表以文件系统**目录**为粒度过滤，I/O 收益比谓词下推更彻底。**建表期就要选好分区键**（常规查询的高频过滤字段，常为日期）。
- **Hive + Spark**：Hive 做元数据（Metastore）与数仓管理、Spark 做执行引擎（Hive on Spark / Spark 读 Hive 表），是分布式数仓的经典组合。表统计信息（ANALYZE TABLE COMPUTE STATISTICS）是 CBO 的养料。

### Structured Streaming 编程模型
- **流计算三要素**：Source（Socket/File/Kafka）→ 流处理引擎 → Sink（Console/File/Kafka/Foreach）。
- **核心抽象：把数据流看作一张不断追加行的"无界表"**，流计算 = 对无界表的批查询。开发者用 readStream 读入 DataFrame → 用普通 DataFrame 算子/SQL 处理 → writeStream 写出。**流处理完全复用 Spark SQL 的引擎与优化能力**。
- **三种输出模式**：Complete（输出至今全量结果）、Update（仅输出本批次有更新的行）、Append（仅输出已定稿的新增行）。
- **容错**：Checkpoint（WAL 预写日志）保障 exactly-once 语义（配合可重放 Source 与幂等/事务 Sink）。

## 关键方法/原理

### Batch mode vs Continuous mode
| 维度 | Batch mode（微批，默认） | Continuous mode（连续处理） |
|---|---|---|
| 机制 | 数据流切成 Micro-batch，每个批次生成作业交给 Spark SQL 优化执行 | 一个 Long Running Job 持续消费，Epoch Marker 划分处理边界 |
| 延迟 | 秒级（作业调度 + Checkpoint WAL 开销） | 毫秒级（先处理数据、后记日志） |
| 吞吐 | 高 | 相对低 |
| 操作支持 | 全部（含聚合） | ⚠️ 仅支持 map/filter/flatMap 等非聚合操作，**聚合类不支持** |
- 选型口诀：要吞吐选微批（绝大多数场景），要毫秒级延迟且无聚合需求的选 Continuous。

### Window 与 Watermark（事件时间处理双件套）
- **两类窗口**：Tumbling Window（滚动，"不重不漏"，各窗口无重叠无遗漏）；Sliding Window（滑动，"可重可漏"，一条数据可属多个窗口）。用 `window(事件时间列, 窗口大小, 窗口间隔)` 在两者间切换，无高下之分、按业务取舍。
- **Watermark（水位线）**：以"最大事件时间 − 容忍延迟"为水位，**决定迟到数据是否还能参与过往窗口的计算与更新**；水位之外的迟到数据被丢弃，从而为过往窗口的状态设定了清理时限。
- 机制本质：没有 Watermark，引擎必须永久保留所有窗口的聚合状态——**Watermark 是状态规模的阀门**。

### 流计算中的数据关联
- **流批关联**：readStream 读流 + read 读批（静态表），普通 Join 语法关联。批侧数据量固定，无需 Watermark/时间范围约束。File Source 用法：format 指定格式 + option 指定监听目录，新文件落入目录即被当作流数据加载。
- **双流关联**：两条流各自缓存对方的状态以等待匹配——**状态数据是双流关联的资源隐患**。必须"双保险"：① 两条流都设 Watermark；② Join 条件中强制限定事件时间范围（如时间戳相差小于 X）。二者共同给状态维护封顶。

### Spark + Kafka（流计算的"万金油"组合）
- Kafka 三大核心功能：连接生产者与消费者、缓存消息、让消费者低延迟访问。基本概念：Broker/Topic/Partition/Offset（消费位点即流处理的 Source 进度）。
- 集成三步（读写同理）：`format("kafka")` 指定 Source/Sink；`option("kafka.bootstrap.servers", ...)` 指定 Broker；`option("subscribe", topic)` 指定读写 Topic。写入时把 DataFrame 组装成 key/value 列即可。

### Catalyst 全景（把 SQL 语句变成高效执行）
- 流水线：Unresolved → Analyzed（结合 Schema 验证表名列名）→ Optimized Logical Plan（81 条启发式规则迭代作用到不动点；Cache Manager 让计划命中已有缓存）→ Spark Plan（策略映射，JoinSelection 选 Join 策略）→ Physical Plan（Preparation Rules，如 EnsureRequirements 自动插入 Exchange/Sort）。
- RBO（规则）→ CBO（统计，"窄慢静"）→ AQE（运行时，见 13 篇）三代优化各占一环，理解 AQE 触发条件（Shuffle Map 完成）才能用对。

## 术语表

| 术语 | 含义 |
|---|---|
| 无界表（Unbounded Table） | Structured Streaming 的核心抽象：流 = 持续追加的表 |
| Micro-batch | 微批，把流切成小批次逐批执行的模型 |
| Continuous mode | 连续处理模型，Long Running Job + Epoch，毫秒级延迟 |
| Watermark | 事件时间水位线，界定迟到数据的容忍窗口并驱动状态清理 |
| Tumbling / Sliding Window | 滚动窗口（不重不漏）/ 滑动窗口（可重可漏） |
| Append / Update / Complete | 三种结果输出模式 |
| Checkpoint / WAL | 流作业的状态与进度持久化，容错与 exactly-once 的基石 |
| File Source | 监听目录、以文件落地为流式数据的 Source 形态 |
| 谓词下推 / 列剪枝 / 分区剪裁 | 过滤贴近数据源 / 只读所需列 / 按目录裁剪分区扫描 |

## 经验与常见坑

- 数仓性能的根在建表期：分区键（高频过滤字段，忌过高基数如 orderId）、文件格式（Parquet/ORC）、统计信息收集——事后补分区 = 把查询时间转嫁给重建表。
- 谓词下推对 CSV 这类无统计信息的格式无效；Parquet 的高压缩率会让"磁盘尺寸"与"内存展开尺寸"严重背离，影响广播阈值判断（见 13 篇坑）。
- 微批的延迟下限由批间隔（trigger interval）决定：设得过小会让调度开销占比飙升、吞吐崩塌，秒级场景别贪毫秒。
- Continuous mode 不支持聚合——"流动的 Word Count"这类最基本需求在 Continuous 下跑不了，选型前先确认操作类型。
- 双流关联漏设 Watermark 或时间范围约束 → 状态无限堆积 → OOM，是最常见的流计算事故。
- 迟到数据被 Watermark 丢弃是"静默丢数"：对准确性敏感的业务要把 watermark 延迟设为业务可容忍的上限，并监控丢弃量。
- 流批关联的批侧若需定时刷新，常见做法是把"批侧"改为周期性 union 新快照或用 foreachBatch 自己控制，此用法演进快，需查最新文档。

## ⚠️ 时效性说明

- Continuous mode 自 Spark 2.3 引入后支持的操作面一直有限（无聚合、有限 Source/Sink），生产采用率低；微批（含可配 trigger 的低延迟微批）仍是事实标准。
- Spark 3.x 后续版本流计算生态大量转向 **Kafka Source v2 / Cloud Files / 流式 Delta Lake**，File Source 监听目录的用法仍有效但已非首选。
- Flink 在"真流式 + 事件时间语义"上后来居上，毫秒级延迟 + 复杂事件时间的生产选型需对比 Flink；Spark 的强项仍是"批流统一在一个引擎里、复用 SQL 生态"。
- Hive on Spark / Spark on Hive 的具体形态随发行版（CDH/COD 等）差异较大，以平台文档为准。