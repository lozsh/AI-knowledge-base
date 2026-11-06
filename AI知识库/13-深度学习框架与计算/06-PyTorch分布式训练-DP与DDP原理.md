---
tags:
  - 分布式训练
  - 深度学习
  - 机器学习系统
  - 训练与优化
---

# PyTorch 分布式训练：从单卡到 DDP

<p class="note-date">更新于 2026-11-05</p>
> 一句话概括：分布式训练 = "谁分布"（数据/模型）× "怎么分布"（单机多卡/多机多卡）；DP 简单但有主卡瓶颈，DDP 是官方推荐的正解。

## 核心概念

### 为什么深度学习用 GPU
普通程序充满 if/else 分支逻辑，擅长者是 CPU；深度学习的计算几乎全是矩阵/向量运算，无分支、流式处理，天然适合 GPU。单卡不够就多卡协同，即分布式训练。

### 两个正交维度
- **谁分布**：数据并行（每个卡拿不同数据）与模型并行（模型切到多卡）。实践中绝大多数场景是**数据并行**。
- **怎么分布**：单机多卡、多机多卡（集群）。

### 单机单卡：一切的基础
三步走：
1. `torch.cuda.is_available()` 判断有无 GPU，`torch.cuda.device_count()` 拿数量；
2. `device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")` 获取设备实例；
3. **迁移**：Tensor 和 Module 都用 `.to(device)` 推上 GPU。

## 关键方法/原理

### DP（nn.DataParallel）：单进程多卡
```python
net = nn.DataParallel(net)   # 一行包住即可
```
运行逻辑：
- 每个 batch 切成 n 份（n = GPU 数），分发到各卡；
- **模型在每个 GPU 上各复制一份**（前向时从主卡复制）；
- 反向传播时**所有卡的梯度汇总到主卡（output_device，默认 0 号）**，主卡求梯度均值、更新参数后再复制回其他卡。

DP 的结构性缺陷：
- 主卡既要汇总梯度、更新模型，又要下发任务，**负载远高于其他卡**（用 nvidia-smi 能看到 0 号卡显存明显更大）；
- 单进程控制，通信效率低，速度慢。

### DDP（DistributedDataParallel）：多进程多卡，官方推荐
每个 GPU 一个进程，**没有主卡**，各卡执行相同任务。核心差异：
- 用 **DistributedSampler** 加载数据：把数据集切成互不重叠的子集，每个进程只读自己那份（各卡从各自硬盘读数据，而不是主卡分发）；
- 反向传播后各进程以**广播（all-reduce）方式汇总平均梯度**，然后各自在本地更新参数，保证所有卡上模型参数始终一致；
- 无需跨卡复制模型，传输数据量更少，**更快且负载均衡**；**同时适用于单机多卡和多机多卡**。

DDP 三要素（进程组概念）：
| 概念 | 含义 |
|---|---|
| group | 进程组，默认只有一个组（一个 world） |
| world_size | 全局进程总数 |
| rank | 进程序号（优先级），rank=0 为主节点 |

DDP 训练四步：
1. **初始化进程组**：`torch.distributed.init_process_group(backend="nccl")`；backend 选 **NCCL（GPU 训练）/ Gloo（CPU 训练）**，init_method 默认 `env://` 从环境变量读配置；
2. **模型并行化**：`net = torch.nn.parallel.DistributedDataParallel(net)`；
3. **分布式数据采样**：
   ```python
   train_sampler = torch.utils.data.distributed.DistributedSampler(train_dataset)
   loader = DataLoader(train_dataset, batch_size=bs, sampler=train_sampler)
   ```
   **注意：sampler 不为 None 时不要设 shuffle**；
4. **启动进程**：`torch.multiprocessing.spawn(main_worker, nprocs=ngpus_per_node, ...)` 为每个节点的每张卡启动一个进程；batch_size 需手动按卡数均分。

### DDP 下的模型保存
多进程下每进程都会执行保存 → **只在主进程（rank 0）保存**，判断 `rank % ngpus_per_node == 0` 或 `args.local_rank == 0`。

## 经验与常见坑
- **DP 不是完整的分布式计算**：只是把部分计算摊到多卡，梯度汇总时"一卡有难，八方围观"。新项目一律上 DDP。
- DP 时 output_device 卡显存明显更大是正常现象，不是显存泄漏。
- 所有参与运算的 Tensor 必须在同一 device 上，混用报 `Expected all tensors to be on the same device`——排查漏 `.to(device)` 的输入或标签。
- 节点数=1 时 DDP 就是单机多卡，代码可以一套通吃单机与集群。
- `CUDA_VISIBLE_DEVICES` 环境变量控制进程可见哪些卡；DataParallel 的切分逻辑可以在 forward 里打印 batch size 验证（每个卡收到 batch_size/n）。
- `nn.ModuleList` 不能像单个模块那样直接调用，要在 forward 里遍历逐层应用。
- 推理阶段与单卡无区别：DDP 只影响训练，保存的权重加载方式不变。

## 术语表

| 术语 | 含义 |
|---|---|
| DP / DataParallel | PyTorch 单进程数据并行 API，有主卡负载瓶颈 |
| DDP / DistributedDataParallel | 多进程数据并行 API，官方推荐，支持单机多卡与多机多卡 |
| DistributedSampler | 分布式数据采样器，为每个进程切分互不重叠的数据子集 |
| world_size / rank | 全局进程总数 / 当前进程编号（rank 0 为主节点） |
| backend（nccl/gloo） | 分布式通信后端：NCCL 用于 GPU，Gloo 用于 CPU |
| 迁移（to(device)） | 把 Tensor/Module 从 CPU 搬到 GPU 的动作 |
| mp.spawn | torch.multiprocessing 的进程启动函数，每卡一进程 |


## 参见
- [AI基础设施与硬件 · 分布式训练](../15-AI%E5%9F%BA%E7%A1%80%E8%AE%BE%E6%96%BD%E4%B8%8E%E7%A1%AC%E4%BB%B6/07-%E5%88%86%E5%B8%83%E5%BC%8F%E8%AE%AD%E7%BB%83.md)——从单机数据并行递进到集群级并行与通信硬件
