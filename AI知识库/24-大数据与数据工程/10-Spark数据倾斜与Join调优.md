# Spark 数据倾斜与 Join 调优：五种策略、广播与倾斜治理工具箱

<p class="note-date">更新于 2026-11-03</p>
> 一句话概括：数据关联的性能问题只有一个主旋律——用 Broadcast 干掉 Shuffle；干不掉时按"大表 Join 小表 / 大表 Join 大表 / 数据倾斜"三种场景套用对应工具箱（AQE、DPP、Join Hints、分而治之、加盐两阶段 Shuffle）。

## 核心概念

### 三种 Join 实现机制
| 机制 | 原理 | 适用 |
|---|---|---|
| Nested Loop Join（NLJ） | 双层循环逐一比对 | 无等值条件（Theta Join）的兜底 |
| Hash Join | Build 阶段小表建哈希表，Probe 阶段 O(1) 探测 | 等值 Join，小表能进内存 |
| Sort Merge Join（SMJ） | 两表按 Key 排序后归并 | 等值 Join，不要求整表进内存，Spark 默认 |

### 五种分布式 Join 策略（按执行效率排序）
**BHJ > SHJ > SMJ > BNLJ > CPJ**（Broadcast Hash Join / Shuffle Hash Join / Shuffle Sort Merge Join / Broadcast Nested Loop / Cartesian）
- 数据分发是分布式 Join 的前提：Shuffle（默认）或 Broadcast。3 种机制 × 2 种分发方式组合出 5 种策略。
- **BHJ 生效前提**：基表能放进内存，且存储尺寸 < 8GB（硬上限）+ 小于广播阈值 `spark.sql.autoBroadcastJoinThreshold`（默认 10MB）。
- JoinSelection 策略选择顺序：BHJ > SMJ > SHJ > BNLJ > CPJ 依次判断先决条件"择优录取"。
- **SHJ 反超 SMJ 的场景**：两表尺寸悬殊（差 3 倍以上即可称"大表 Join 小表"）且小表数据分布均匀、每个分片能进内存——小表建哈希表的开销小于两表排序。用 `/*+ shuffle_hash(小表) */` 强制。

### 让 Spark SQL 走 Broadcast 的三种方法
1. 调配置：`spark.sql.autoBroadcastJoinThreshold`（经验锚点：主动调大到 **1-2GB** 往往值得，配合对内存展开尺寸的评估）
2. Join Hints：`/*+ broadcast(表) */`（或 broadcastjoin/mapjoin）
3. API：`broadcast(df)` 函数包裹小表
- 原则：**以广播阈值配置为主、强制广播为辅**。广播不是银弹：小表再大也不能超 8GB；广播还吃 Driver 与网络（全量数据经 Driver 分发到每个 Executor）。

## 关键方法/原理

### AQE（自适应查询执行，Spark 3.0）
- **触发时机：每当 Shuffle Map 阶段执行完毕**，依据中间文件统计信息（data 文件大小、空文件占比、分区大小）动态修正尚未执行的计划。**没有 Shuffle 的查询 AQE 完全无效**。
- 优化背景：RBO（规则，经验主义，81 条规则归三类：谓词下推、列剪枝、常量替换）→ CBO（统计信息驱动，但"窄、慢、静"：仅支持 Hive Metastore 表、ANALYZE 收集慢、计划制定后不随运行时变化）→ AQE（运行时动态）。
- 三大特性与关键配置：
  1. **Join 策略调整**：Map 阶段结束后若某表中间文件总尺寸 < 广播阈值且空文件占比 < `spark.sql.adaptive.nonEmptyPartitionRatioForBroadcastJoin`（默认 0.2），SMJ 降级 BHJ。降级判定必须等两表 Shuffle Map 都完成；靠 **OptimizeLocalShuffleReader**（`...localShuffleReader.enabled` 保持 true）让 Reduce 就地读本地文件、省掉网络分发——"亡羊补牢，犹未为晚"。注意：**只有 SMJ 能降级**。
  2. **自动分区合并**：按分区编号顺序合并过小分区。目标尺寸 = min(advisoryPartitionSizeInBytes, 总量/minPartitionNum)——并非设多大就多大。
  3. **自动倾斜处理**：拆大分区。倾斜判定 = 分区 > 中位数 × `skewedPartitionFactor`（默认 5）**且** > `skewedPartitionThresholdInBytes`（默认 256MB），两个条件同时满足。
- 倾斜处理的本质局限：**以 Task 为粒度**。倾斜分区若集中在少数 Executor 上，拆分只平衡了 Executor 内部，Executor 间的负载失衡依旧——此时需要手工方案。

### DPP（动态分区剪裁，Spark 3.0）
- 运行时用**维度表的过滤结果**裁剪**事实表**的分区扫描（把维表过滤条件经关联关系传导到事实表）。
- 三个先决条件：① 仅支持等值 Join；② 维表过滤后 < 广播阈值；③ **事实表是分区表且分区字段包含 Join Key**。
- 与谓词下推的区别：谓词下推靠文件注脚统计信息过滤文件（受"纯度"限制）；分区剪裁以目录为粒度裁剪，I/O 收益更大。DPP 自动触发、无需配置，但依赖数仓建表时就把 Join Key 设计成分区键——**表结构要在数仓规划期设计好，临时抱佛脚等于把查询时间转嫁给建表**。

### 大表 Join 小表：小表超广播阈值的三案例
1. **Join Keys 远大于 Payload**（如 6 个长维度做关联键）：把 Join Keys 拼接后哈希（MD5/SHA-256）成单一短 Hash Key 列替代原始键，内表删掉原始键后从 10GB 缩到 1.5GB，进广播。防哈希冲突用**二次哈希**（两种哈希算法结果拼接）。
2. **过滤条件选择性高**（星型模型维表带 `type='Head User'` 类过滤，过滤后占比千分之一量级）：开 AQE 让 SMJ 运行时降级 BHJ（实测 5 小时 → 30 分钟）；再补 DPP（重建事实表按 Join Key 分区后 30 分钟 → 15 分钟）。
3. **小表分布均匀且无过滤**：Join Hints 强制 SHJ 替代 SMJ（实测 7 小时 → 5 小时）。前提是小表各分片都能进内存，否则倾斜分片必 OOM。

### 大表 Join 大表：分而治之 + 负隅顽抗
- 行业共识：大表 Join 大表是数仓设计缺陷的信号，能避免就避免。
- **分而治之**：内表按基数适中、分布均匀的列（**日期列通常是最佳选择**，同时享受分区剪裁）拆成多个可广播的子集，外表逐个与之做 BHJ，结果 Union。关键配套是**避免外表重复扫描**：要么全量 Cache（内存门槛高），要么靠 DPP（外表以 Join Key 为分区键，每个子查询只扫对应分区，全量恰好只扫一遍）。
- **负隅顽抗**（必须走 Shuffle Join 时）：
  - 数据均匀 → 强制 SHJ；分片进不了内存就回到 12 篇"三足鼎立"公式调并行度/并发度/内存。
  - 数据倾斜 → 见下方工具箱。

### 数据倾斜治理工具箱（从轻到重）
1. **AQE 自动倾斜**：单边倾斜、倾斜分布相对均匀时首选，零开发成本（3 个参数调好即可）。
2. **提高并行度打散**：分区粒度变小，轻度倾斜自然稀释（`spark.sql.shuffle.partitions` / repartition）。
3. **过滤异常 Key**：倾斜源若是脏数据（如 null、默认值），先过滤或单独处理，成本最低。
4. **Map 端预聚合**：聚合类需求用 reduceByKey 类算子，倾斜在 Map 端被先消化。
5. **广播小表**：BHJ 天然免疫倾斜（无 Shuffle）——能广播就广播。
6. **加盐两阶段 Shuffle**（倾斜集中于少数 Executor 时的手工方案）：
   - 按 Join Key 是否倾斜把内外表各拆两部分：均匀部分走 SHJ；倾斜部分走加盐流程。
   - 第一阶段"加盐、Shuffle、关联、聚合"：**外表随机加盐**（Key 加 1..N 随机后缀，N 取 Executor 总数，打散倾斜）；**内表复制加盐**（每条记录复制 N 份、各带固定后缀 1..N，保持关联关系）。Shuffle 后倾斜被摊到所有 Executor。
   - 第二阶段"去盐化、Shuffle、聚合"：去掉后缀，按原始 Key 二次聚合，还原业务逻辑。两段结果 Union。
   - 代价：内表膨胀 N 倍 + 两次 Shuffle + 显著开发成本——**只有 Executor 级倾斜确属瓶颈时才值得投入**。
7. 不适用场景：加盐破坏组内有序性（全局排序需求）、不可二次聚合的聚合（如平均值需改部分聚合语义）。

## 术语表

| 术语 | 含义 |
|---|---|
| BHJ / SHJ / SMJ | 广播哈希 / Shuffle 哈希 / Shuffle 排序归并 Join |
| Join Hints | SQL 注释形式 `/*+ broadcast(表) */` 把专家经验凌驾于优化器之上 |
| Selectivity（选择性） | 过滤条件筛掉的比例；选择性越高过滤后越小，越利于广播 |
| 内表 / 外表 | Join 中较小/较大的一方；分而治之拆内表、避免重复扫外表 |
| 加盐（Salting）/ 去盐化 | 给倾斜 Key 加随机/固定后缀打散 / 去后缀还原聚合 |
| DemoteBroadcastHashJoin | AQE 把 SMJ 降级为 BHJ 的逻辑规则 |
| OptimizeLocalShuffleReader | AQE 降级 BHJ 后让 Reduce 就地读本地 Shuffle 文件 |
| OptimizeSkewedJoin | AQE 拆倾斜分区（并复制对侧对应分区）的策略 |
| DPP | 动态分区剪裁，运行时以维表过滤结果裁剪事实表分区 |
| EnsureRequirements | 物理计划阶段自动插入 Exchange/Sort 满足算子输入要求 |

## 经验与常见坑

- 广播阈值判断依据磁盘统计值：Parquet 列裁剪后实际广播的内存展开尺寸可能远超预期 → Driver OOM；判大小用 cache + 执行计划统计值。
- AQE Join 降级只有 SMJ 支持；`localShuffleReader.enabled` 千万别手动关。
- AQE 倾斜判定是双条件（中位数×5 且 >256MB），只调一个参数可能不生效；advisoryPartitionSizeInBytes 会被 minPartitionNum 反推值压制，并非"设多大是多"。
- 双边倾斜时 AQE 需 M×N 份分区复制，开销可能失控——退回手工加盐方案。
- "大表 Join 小表"定义只看比例（3 倍以上），不代表小表能进广播；分场景套案例 1/2/3。
- 分而治之的 for 循环写法不是"单机思维"：只要外表靠 DPP/分区避免重复扫描，形式上的循环是合理的分布式拆解。
- 给事实表的 Join Key 设分区键会带来海量小分区（如 orderId 基数过高）→ NameNode 压力与调度开销；分区键要选基数适中的列，或对高基数列做尾号等映射后再分区。

## ⚠️ 时效性说明

- AQE/DPP 为 Spark 3.0 特性（Spark 3.0/3.1 中 AQE 默认关闭，`spark.sql.adaptive.enabled=true` 开启；**Spark 3.2+ AQE 默认开启**）；2.x 用户只能用广播阈值 + Join Hints + 手工加盐。
- 广播 8GB 上限、阈值默认 10MB 等数值为 Spark 3.0 当时的版本行为，具体以所用版本官方文档为准。
- Spark 3.x 后续版本新增了多种 Join Hints 变体与 AQE 配置项，工具箱思路不变、参数名需核对。