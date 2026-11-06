---
tags:
  - 深度学习
  - 神经网络
  - 机器学习系统
---

# PyTorch 核心心智模型：Tensor 与自动求导

<p class="note-date">更新于 2026-11-03</p>
> 一句话概括：PyTorch 的一切计算围绕 Tensor 展开，学习的一切动力来自 autograd 自动求导 + 梯度下降。

## 核心概念

### Tensor = 统一的数据表示
- 标量（Rank 0）、向量（Rank 1）、矩阵（Rank 2）及更高维数组，统一叫张量（Tensor），用 **Rank（秩）** 表示"维度"。
- Tensor 与 NumPy 数组的关系：都是科学计算的数据表示，语法高度相似；**本质区别是 Tensor 可以上 GPU 加速，NumPy 不能**。
- 典型工作流：数据处理阶段用 NumPy → `torch.from_numpy()` 转 Tensor → 进模型训练。

### 自动求导（autograd）的心智模型
- 模型学习 = 不断减小损失函数值。减小手段是**梯度下降**：每次参数更新沿梯度**反方向**走（梯度方向是函数值增长最快的方向，反方向即下降最快方向）。
- 数学链条：导数 → 偏导数（固定其他变量、只对一个变量求导）→ 梯度（所有偏导数构成的向量）→ 链式法则（复合函数求导，`dy/dx = dy/du · du/dx`）→ 反向传播。
- 反向传播三步循环：
  1. **前向传播**：数据从输入层 → 隐藏层 → 输出层，单向流动；
  2. **计算误差并反向传播**：从输出层向输入层逐层回传误差；
  3. **迭代更新参数**，直到收敛。
- PyTorch 已完整封装反向传播，开发者只需写前向 + 调 `loss.backward()`；但必须理解其运转方式才能调试。
- `requires_grad=True` 的 Tensor 才会被求导，导数值存进 `.grad` 属性，供优化器更新参数。**训练时设 True，验证/测试时关掉**，避免参数随 loss 漂移。

## 关键方法/原理

### Tensor 常用操作模式（API 细节查文档，模式要记牢）
| 操作类别 | 代表函数 | 关键心智点 |
|---|---|---|
| 创建 | `torch.tensor / zeros / ones / eye / rand / randn / normal / randint` | `rand` 是 0~1 均匀分布；`randn` 是标准正态分布 |
| 类型/设备转换 | `.item()`（Tensor→标量）、`data.cuda()` / `data.cpu()` | CPU↔GPU 转换本质是换 device |
| 查形状 | `.shape`（属性）/ `.size()`（方法）/ `.numel()` | 设计网络时必须时刻对 Tensor 形状了如指掌 |
| 维度交换 | `permute()`（任意多维）/ `transpose()`（一次两维） | 交换后 Tensor **内存不再连续** |
| 形状变换 | `view()` / `reshape()` | `view` 只能处理内存连续的 Tensor；`reshape` = 先捋顺内存再 view |
| 增减维度 | `squeeze(dim)`（删大小为 1 的维度）/ `unsqueeze(dim)`（插一个大小为 1 的维度） | 只增减"1"维，不改变元素数量 |
| 连接 | `torch.cat`（沿已有维度拼接，不升维）/ `torch.stack`（新建维度堆叠，升维） | 单通道图合并成多通道用 stack |
| 切分 | `chunk`（按份数均分，先除后向上取整）/ `split`（按每份大小切，支持列表指定各份大小）/ `unbind`（降维切分，去掉一个维度） | 返回的都是 tuple |
| 选择 | `index_select`（按索引，mask 需为 Tensor）/ `masked_select`（按布尔掩码，返回一维） | `tensor[mask]` 等价于 `masked_select` |

### 梯度确认（gradient checking）调试法
数值微分（梯度下降的原始形式）实现简单但慢；反向传播快但容易写错。工程上用两者结果对比来验证手写反向传播的正确性，称为**梯度确认**。

## 经验与常见坑
- **`torch.Tensor()` vs `torch.tensor()`**：前者是类（`torch.FloatTensor` 的别名，始终输出 float32，且不拷贝数据）；后者是函数（按输入类型推断，会拷贝数据）。日常用 `torch.tensor()` 更安全。
- **梯度会累加**：PyTorch 每次 backward 的梯度是累加的，每个 batch 训练前必须 `optimizer.zero_grad()`（或 `model.zero_grad()`），否则第二次的梯度 = 第一次 + 第二次。
- **view 报错 "view size is not compatible..."**：Tensor 经 transpose/permute 后内存不连续，`view` 会失败。改用 `reshape`，或先 `.contiguous()` 再 `view`。
- **chunk 不整除时的分法**：先做除法再向上取整。如 17 切 4 份得 5,5,5,2 而不是 4,4,4,5。
- **维度/大小参数必须提前算清楚**：cat、chunk、split 的 dim 和 size 出错不会立刻报错，往往到后续层才炸。
- **split 返回的是原输入的视图**：对 split 结果的操作会影响原数据。

## 术语表

| 术语 | 含义 |
|---|---|
| Tensor / 张量 | PyTorch 统一的多维数组结构，可上 GPU |
| Rank（秩） | Tensor 的维度阶数，标量 0 阶、向量 1 阶、矩阵 2 阶 |
| requires_grad | 标记 Tensor 是否需要在计算中保留梯度 |
| autograd | PyTorch 的自动微分机制，自动完成反向传播 |
| 梯度（gradient） | 函数所有偏导数构成的向量，方向指向函数值增长最快处 |
| 链式法则 | 复合函数求导规则，反向传播的数学基础 |
| 反向传播（Backpropagation） | 误差从输出层向输入层逐层回传并更新参数的算法 |
| 梯度确认 | 用数值微分对照反向传播结果验证实现正确性 |
| 内存连续（contiguous） | Tensor 数据在内存中按行优先连续存放；view 要求连续 |