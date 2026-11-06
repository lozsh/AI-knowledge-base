---
tags:
  - 大数据
  - 基础设施
  - 数据中心
  - 数据工程
---

# Google 分布式系统谱系：从三驾马车到 Spanner 与 Borg

<p class="note-date">更新于 2026-11-05</p>
> GFS/MapReduce/Bigtable 三驾马车定下"廉价 PC 集群跑海量数据"的范式，其后 Megastore→Spanner 补齐事务与全球一致性，Borg→Omega→Kubernetes 补齐资源编排——每一代系统都是为了解决上一代的明确短板。

## 核心概念

**大数据三理念**（整个生态的公理）：
1. 集群可伸缩到 1000 台以上服务器（2003 年 GFS 之前，并行数据库单集群只有几十台）；
2. 用廉价 PC 架构搭建，不用小型机/专用存储——这让技术能在大中小公司间扩散；
3. "把数据中心当作一台计算机"（Datacenter as a Computer）：开发者像面对单机一样编程，不操心可用性与一致性。

三者分别让海量处理"可能、便宜、容易"。

**谱系一览**（每代系统解决前一代的不足）：

| 系统 | 年份 | 解决什么 | 引入什么新权衡 |
|---|---|---|---|
| GFS | 2003 | 上千节点存储，高吞吐 | 单 Master + 放宽一致性（至少一次追加写） |
| MapReduce | 2004 | 海量数据的通用批处理 | 每轮读写磁盘，低延迟/迭代差 |
| Chubby | 2006 | 集群共识与分布式锁 | Paxos 工程化，粗粒度锁 |
| Bigtable | 2006 | 大集群下高性能随机读写 | 无跨行事务、无 SQL、无 Schema |
| Hive | 2009 | SQL 门槛 + 数据仓库 | 底层仍是 MapReduce，延迟高 |
| Dremel | 2010 | 秒级交互式 OLAP | 只读嵌套数据、结果近似 |
| Spark/RDD | 2010 | 迭代与内存计算 | 用血缘（Lineage）换容错 |
| Megastore | 2011 | Bigtable 之上的 Schema/事务/异地多活 | 写延迟 100-400ms，性能低 |
| Spanner | 2012 | 全球一致 + 外部一致性事务 | 依赖 TrueTime 硬件时钟 |
| Borg/Omega/K8s | 2013-2015 | 混合部署、提高利用率 | 调度从单 Master 走向乐观并发 |

## 关键设计/原理

### GFS（存储层）

- **单 Master + 64MB 大 Chunk**：Master 元数据（每文件约 100B）全放内存，一台 64GB Master 可管 6 亿文件/约 15PB；真正的瓶颈在网络而非 Master。
- **控制流与数据流分离**：客户端只向 Master 要元数据，数据直接与 chunkserver 流水线传输；Lease（租约，默认 1 分钟）指定 primary 决定写顺序，尽量减少 Master 参与。
- **CAP 取舍**：保 A（可用性）放 C（一致性）。追加写只保证**至少一次**，部分节点写失败的"脏数据"直接暴露给应用，由应用去重排序——用应用复杂度换系统简洁。
- **高可用**：Master/Backup Master/Shadow Master 三层 + chunk 多副本；Snapshot 时把待写 chunk 先拷贝一份再写，不阻塞写入。

### MapReduce（计算层）

- 借鉴 Lisp 函数式思想，`map: (k1,v1)→list(k2,v2)`、`reduce: (k2,list(v2))→list(v3)`，**分离业务逻辑与控制逻辑**，分布式细节全部交给框架。
- 架构与 GFS 同款：单 Master 调度 + Worker 执行；Map 输出落本地盘，Reduce 经 Shuffle 按 R 份分区拉取；Master 故障不做自动恢复（任务重跑）。
- 关键优化：**计算靠近存储**（Locality）、**Combiner**（减少 Shuffle 数据）、**Backup Tasks**（对长尾任务双跑取先完成者——曾把拖慢 44% 的长尾消除）。
- 实测缺陷：Worker 初始化占了 Grep 任务 150 秒中的 60 秒（40%），中间结果必落盘——这正是 Hive/Dremel/Spark 的进化起点。

### Dremel（交互式分析层）

- 定位是 MapReduce 的**补充**而非替代：Dremel 几秒出近似结果供快速验证想法，精确分析仍要写 FlumeJava/MapReduce。它处在"分析师探索"环节。
- 列存的好处：只加载查询涉及的列 + 压缩更廉价省 CPU。论文实测同一查询 MapReduce-on-records 读 87TB 花数小时，MapReduce-on-columns 只读 0.5TB 缩到几分钟——光是把 MapReduce 跑在列存上就提升一个数量级。
- **难点是嵌套数据怎么还原**。Dremel 给每个字段值附加两个整数：
  - **Repetition Level**：字段路径上，第几个可重复字段最近发生了重复（0 表示新记录开始），用于知道"这条记录里该字段出现了几条"；
  - **Definition Level**：字段路径上，那些"可以不定义"的子字段（可选/可重复）实际出现了几个，用于区分 NULL 是"字段不存在"还是"哪一级不存在"。
  - 两者让每个值**自描述嵌套结构信息**，配合状态机（Record Assembly）即可从列数据重建原始记录。这套编码就是 Parquet 的内核。
- **多层查询执行树**：根服务器接收请求、分解查询计划、聚合最终结果；中间服务器（可多层）进一步分解与聚合；叶子服务器在各数据分片上执行。分析查询逐层聚合后数据量递减，所以网络开销不随层数爆炸，层数越多并行度越高、延迟越低。
- Dremel 2020 回顾论文补充的降延迟手段：服务池化（避免冷启动）、投机执行（快机器多干）、只解析查询涉及列的 Schema、轻量压缩、近似结果（处理完 98% 就返回可降 2-3 倍延迟）、查询延迟层（小查询不被大查询阻塞）、文件元信息复用、重要作业容量保障、自适应执行树层数。

### Bigtable（在线服务层）

- 数据模型：**有序稀疏表**，行键原子读写；列族（Column Family）物理聚合（≠列式存储）；每个单元格多版本带时间戳。
- 运维性是核心动机：MySQL 集群分区不灵活、扩容要搬数据、故障不能自动恢复；Bigtable 用**动态行键范围分区（Tablet，超阈值一分为二）+ Tablet Server 服务池**解决，容灾从"指定一台备份"变成"备份池里随便挑"。
- 三层分区定位：Chubby 文件 → Root Tablet（永不分裂）→ METADATA 分区 → 数据 Tablet。Master 只做调度，单点不成为瓶颈。
- **百万级随机读写两板斧**：随机写变顺序写（Commit Log + MemTable + SSTable）；读尽量走内存（MemTable → 缓存 → SSTable）。配套：布隆过滤器跳过无关 SSTable、块索引、SSTable 不可变免锁、Major/Minor Compaction。

### Chubby 与 Paxos（共识层）

- 两阶段提交解决跨节点原子性但存在协调者单点 → 需要共识算法选主。**可串行化（事务级顺序）≠ 可线性化（单操作顺序）**，分布式共识保证的是全集群按一致顺序执行操作。
- Paxos 两轮提议（Prepare + Accept）的原因：多个提案者并发时，提案者必须先获知最新提案编号才能保证顺序；单一提案者时可简化为一轮——这就是 Multi-Paxos 的优化思路。
- Chubby 把 Paxos 封装成**粗粒度分布式锁服务**（锁可持有数小时/天）而非协议库：侵入性小、便于发布订阅、开发者熟悉锁接口、应用无需自管多节点。服务端 5 节点，三层结构：Paxos 日志复制 → 简单 KV → 锁服务。GFS 用它选主，Bigtable 用它做 Master 选举、Tablet Server 发现与客户端路由。

### Megastore → Spanner（数据库层）

- Megastore 首次在 Bigtable 上补关系型特性：**实体组（Entity Group）**按 Key 预 Join 物理连续存储，利用数据局部性；组内一阶段事务 + MVCC 乐观并发（Bigtable 多版本天然支持）；组间要么两阶段事务要么异步消息。
- 每个实体组一个 Paxos 组跨数据中心同步复制：组内顺序、组间并发。**快速读**靠 Coordinator 记录"本地哪些数据最新"（代价：写要通知全部副本而非多数派）；**快速写**用无租期的 Leader-based Paxos（Leader 故障立即重选，通常选出离用户最近的 DC）。实测写延迟 100-400ms——示范意义大于性能。
- Spanner"重写"了一切：放弃 Bigtable，Spanserver 的 Tablet 自身兼任 Paxos Group 节点、副本承担锁表与事务管理；**Pipelined Paxos**（有租期 Leader，后续提议在 Leader 排队，一阶段完成）替代 Megastore 频繁退回两阶段。
- **TrueTime 是点睛之笔**：任何服务器本地时钟都不准（石英振荡器日误差约 1 秒），分布式事务无论取谁的本地时间做提交时间戳都有"后事务读不到前事务数据"的悖论。Spanner 的解法是 ① 用原子钟+GPS 把全集群时钟误差压缩到一个已知区间 [earliest, latest]；② 提交前**等待误差区间完全过去**（commit wait）。由此获得全局单调递增的提交时间戳，实现**外部一致性**（可串行化 + 可线性化：前事务写入，后事务立即可见）。读侧用 $t_{safe} = \min(t_{paxos\_safe},\ t_{TM\_safe})$ 判断副本能否安全响应指定时间戳的读（$t_{safe}$ 为副本的安全读时间戳，$t_{paxos\_safe}$ 为 Paxos 组已达成一致的安全时间，$t_{TM\_safe}$ 为事务管理器认可的安全时间）。

### Borg → Omega → Kubernetes（资源编排层）

- 动机是成本：数据中心运营成本过半是电费，按峰值采购导致深夜大量闲置 → 混合部署（在线服务 + 批处理 + 业务系统共居一集群）"削峰填谷"。
- 底座是 Linux **CGroups**（资源限制/优先级/结算/冻结），Borg 任务即封装好的 LXC 容器。一个 Cell 约 1 万台机器。
- Borg 架构仍是经典 Master-Slave：Master 集群 Paxos 复制元数据、master-of-masters 靠 Chubby 锁选主；调度器（Scheduler）从 Master 剥离；Borglet 管 Slave、定期上报。优先级：监控 > 生产 > 批处理 > 尽最大努力；生产可抢占批处理，**alloc 机制**为定时报表类批任务预留不可抢占资源。
- 单 Master 调度成为瓶颈：在线服务调度是 NP-Hard、单次要算几十秒，阻塞同一队列里的秒级 SQL Job。**Omega** 的解法：多调度器并存，把"第一层调度器"退化成带 MVCC 的**共享状态数据库**，各调度器以**乐观事务**竞争资源，失败重试——悲观锁（Mesos 式两层调度 + Resource Offer，需长期锁资源）换乐观锁。
- Kubernetes 的教训：真实编排还需**环境隔离**（镜像解决"DLL 地狱"）与服务发现/负载均衡（kube-proxy 免侵入式服务依赖管理）。所以 K8s 不是调度器，而是容器"编排"系统。

## 术语表

| 术语 | 含义 |
|---|---|
| Chunk / Tablet | GFS 的文件分片（64MB）/ Bigtable 的行键范围分区 |
| SSTable / MemTable | 不可变有序磁盘文件 / 内存写缓冲，二者构成 LSM 写路径 |
| Lease（租约） | 有时限的授权，用于指定 primary/Leader，防"僵尸写者" |
| Paxos / Multi-Paxos | 分布式共识算法 / 单提案者优化（两轮变一轮） |
| 可串行化 vs 可线性化 | 事务级全序 vs 单操作全序 |
| 外部一致性 | 比线性更强：事务全序 + 实时序（前写后读立即可见） |
| TrueTime | 原子钟+GPS 支撑的带误差区间的时间 API |
| Entity Group / 目录 | Megastore/Spanner 中按 Key 预 Join 的数据亲缘单元 |
| Cell / Borglet / alloc | Borg 集群 / 节点代理进程 / 不可抢占资源预留 |
| MVCC | 多版本并发控制，读写互不阻塞，靠时间戳/版本判断可见性 |

## 经验与常见坑

- **每一代系统都在还上一代的债**：Bigtable 放弃事务 → Megastore 补 → Megastore 写太慢 → Spanner 重写；MapReduce 慢 → Hive 补门槛、Dremel 补延迟、Spark 补迭代。评估新系统先问"它在补谁的什么短板"。
- **CAP 在工程里是"选边 + 放宽"而非死二选一**：GFS 选 AP、Spanner 用硬件（原子钟）把"不可能三角"中的一角做便宜了——真正的取舍常发生在成本维度。
- **单 Master 不一定是瓶颈，关键看 Master 的参与度**：GFS/Bigtable 的 Master 只碰元数据与调度，数据面完全绕开；把"控制流与数据流分离"作为通用设计直觉。
- **粗粒度 > 细粒度**：Chubby 粗粒度锁（小时/天级）、Kafka 批量提交 Offset、MillWheel 批量 Checkpoint——细粒度语义往往被批量执行取代，ZooKeeper/Chubby 是共识协调而非高性能 KV，别拿它存高频状态。
- **可运维性是被低估的一等需求**：Bigtable 胜出 MySQL 集群，先是赢在动态分区/自动故障恢复，其次才是性能。
- **用领域特性换通用性能**：Dremel 的近似结果、分析查询"逐层聚合数据量递减"支撑多层执行树、Kafka 容忍丢几条日志换吞吐——先明确业务能容忍什么，再谈架构。

## ⚠️ 时效性说明

- GFS 后继 Colossus、以及 MapReduce 在 Google 内部已被 FlumeJava/Dataflow 取代，均无公开论文细节；MapReduce 作为引擎在工业界也已被 Spark 等替代，但其编程模型与容错设计仍是理解一切批处理系统的地基。
- Kafka 早期版本依赖 ZooKeeper 存 Offset/所有权注册表，新版（KRaft 之后）已去 ZooKeeper；ZooKeeper 方案为 2011 论文时期的机制。
- 本文基于 2021 年技术认知；Spanner 论文中"论文当年用 TT.now().latest 做跨组读时间戳"属于实现细节，现实现或有变化。Chubby 在 Google 内部仍服务，但开源世界的对应物是 ZooKeeper/etcd。