---
tags:
  - 神经网络
  - 深度学习
  - 训练与优化
  - 分类
---

# softmax 回归与图像分类

<p class="note-date">更新于 2026-11-06</p>

**一句话定义**：softmax 回归是把线性模型推广到多分类的单层神经网络——仿射变换产出各类别的未规范化得分，softmax 函数把它们变成概率分布，配合交叉熵损失与 Fashion-MNIST 基准，构成图像分类入门的完整流程。

## 核心原理

### 分类问题的表示

分类回答"哪一个"。类别无自然顺序时（猫/鸡/狗）用**独热编码**：$y \in \{(1,0,0), (0,1,0), (0,0,1)\}$。有自然顺序时（年龄分组）转回归保留整数格式才有意义。

### 模型：单层网络 + softmax

每类一个仿射函数输出未规范化的预测（logit）：$o = Wx + b$，其中 $W \in \mathbb{R}^{q \times d}$（$d$ 个输入、$q$ 个类别的权重矩阵），再用 softmax 把 $o$ 变成概率：

$$\hat{y}_j = \frac{\exp(o_j)}{\sum_k \exp(o_k)}$$

为什么要 softmax 而不直接把 $o$ 当概率：$o$ 的总和不为 1、且可能为负，违反概率公理。softmax 求幂保证非负、除以总和保证归一、保持可导。它不改变 $o$ 的大小次序（$\arg\max\, \hat{y} = \arg\max\, o$），且**虽然 softmax 是非线性函数，softmax 回归的输出仍由仿射变换决定——它仍是线性模型**。

小批量矢量化：$O = XW + b$（$O \in \mathbb{R}^{n \times q}$），softmax 按行执行。

> **全连接层的参数开销**：$d$ 输入 $q$ 输出的全连接层参数量为 $O(dq)$，实践中可能高得惊人；可用超参数 $n$ 将开销降到 $O(dqn)$（分流方法）。

### 损失：交叉熵（最大似然）

对独热标签，负对数似然化为 $l(y, \hat{y}) = -\sum_j y_j \log \hat{y}_j$——只留下正确类那一项。代入 softmax 定义可推出**漂亮的梯度**：

$$\partial_{o_j} l = \text{softmax}(\mathbf{o})_j - y_j$$

即梯度 = 预测概率 − 真实标签，与线性回归中"梯度 = $\hat{y} - y$"完全同构（这不是巧合：任何指数族分布的对数似然梯度都是这个形式）。

### 信息论解释

- **熵** $H[P] = -\sum_j P(j) \log P(j)$：编码从分布 $P$ 抽取的数据所需的最少"纳特"数（1 纳特 = $1/\log 2 \approx 1.44$ 比特，纳特用自然对数底）；
- **信息量** = $-\log P(j)$：事件概率越低，发生时"惊异"越大；熵是概率匹配真实数据生成过程时信息量的期望；
- **交叉熵** $H(P, Q)$：主观概率为 $Q$ 的观察者看到按 $P$ 生成的数据时的预期惊异；$P = Q$ 时最小，等于 $H(P)$。交叉熵分类目标的两面：① 最大化观测数据似然；② 最小化传达标签所需的惊异。

## 经验与常见坑

- **softmax 数值稳定性（最重要的实现细节）**：$o_k$ 很大时 $\exp(o_k)$ 会**上溢**（inf），$o_j - \max$ 后大负值会**下溢**（0），$\log(0) = -\infty$，反向传播几步后满屏 nan。技巧：softmax 前先对所有 $o_k$ 减去 $\max(o_k)$——减常数不改变 softmax 结果；更好的做法是**把未规范化的预测直接传入交叉熵损失**（PyTorch 的 `nn.CrossEntropyLoss`），在损失内部合并计算 softmax 与 log（LogSumExp 技巧），$\log(\exp(\cdot))$ 相互抵消，彻底避开数值问题。
- **交叉熵取标签概率的实现**：`y_hat[range(len(y_hat)), y]` 用 y 做花式索引一行取正确类概率，避免低效 for 循环。
- **sum 沿轴与 keepdim**：`X.sum(0, keepdim=True)` 保持轴数（形状 (1,3)），便于后续广播。
- **训练-评估分离**：测试集只用于评估精度（accuracy = 正确预测数/预测总数），绝不参与训练。
- **softmax 之名是误称**：真正的 soft-softmax 是 $\text{RealSoftMax}(a,b) = \log(e^a + e^b)$，当 $\lambda \to \infty$ 时 $\lambda^{-1}\text{RealSoftMax}(\lambda a, \lambda b) \to \max(a, b)$。

## 代码模式：Fashion-MNIST 分类全流程

**数据集**：Fashion-MNIST（10 类服饰灰度图，28×28×1，训练 60000 / 测试 10000），比 MNIST 复杂、比 ImageNet 轻量，是分类入门标准基准。10 类：t-shirt、trouser、pullover、dress、coat、sandal、shirt、sneaker、bag、ankle boot。

```python
trans = transforms.ToTensor()  # PIL → 32位浮点，除以 255 归一到 [0,1]
mnist_train = torchvision.datasets.FashionMNIST(root="../data", train=True,
                                                transform=trans, download=True)
train_iter = data.DataLoader(mnist_train, batch_size, shuffle=True)

# 从零版模型：图像先 reshape 展平为向量，再仿射 + softmax
def net(X):
    return softmax(torch.matmul(X.reshape((-1, W.shape[0])), W) + b)

# 简洁版：直接用框架层，CrossEntropyLoss 内含 softmax + log（数值稳定）
net = nn.Sequential(nn.Flatten(), nn.Linear(784, 10))
loss = nn.CrossEntropyLoss(reduction='none')
trainer = torch.optim.SGD(net.parameters(), lr=0.1)

# 预测：取概率最大的类别
preds = net(X).argmax(axis=1)
```

训练超参数：学习率 0.1、10 个 epoch 左右即可在 Fashion-MNIST 上达到 80%+ 精度。训练循环与线性回归完全一致——**读取数据 → 定义模型与损失 → 优化算法训练**，几乎所有深度学习模型都复用这一流程。

## ⚠️ 时效性说明

本篇 API 以 PyTorch 当前长期稳定用法为准（`torchvision.datasets.FashionMNIST` 等）；MNIST 作为基准已过于简单，新研究不再使用；"全连接层参数开销可用 $O(dqn)$ 降维"是分流式设计的早期表述，现代大模型中这一思想演化为 MoE、低秩分解等技术。

## 参见
- [线性回归](02-%E7%BA%BF%E6%80%A7%E5%9B%9E%E5%BD%92.md) —— 同域前置：从回归到分类的基础
- [多层感知机](04-%E5%A4%9A%E5%B1%82%E6%84%9F%E7%9F%A5%E6%9C%BA.md)
- [数学与机器学习基础 · 预备知识](../02-%E6%95%B0%E5%AD%A6%E4%B8%8E%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0%E5%9F%BA%E7%A1%80/02-%E9%A2%84%E5%A4%87%E7%9F%A5%E8%AF%86.md)
- [数学与机器学习基础 · 机器如何自己学习](../02-%E6%95%B0%E5%AD%A6%E4%B8%8E%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0%E5%9F%BA%E7%A1%80/04-%E7%BB%8F%E5%85%B8%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0%E6%A8%A1%E5%9E%8B%EF%BC%9A%E4%BB%8E%E7%BA%BF%E6%80%A7%E5%9B%9E%E5%BD%92%E5%88%B0%E9%9B%86%E6%88%90%E5%AD%A6%E4%B9%A0.md)
- [模型训练与优化 · 优化算法](../12-%E6%A8%A1%E5%9E%8B%E8%AE%AD%E7%BB%83%E4%B8%8E%E4%BC%98%E5%8C%96/02-%E4%BC%98%E5%8C%96%E7%AE%97%E6%B3%95.md)
- [深度学习框架与计算 · PyTorch模型构建与训练全流程](../13-%E6%B7%B1%E5%BA%A6%E5%AD%A6%E4%B9%A0%E6%A1%86%E6%9E%B6%E4%B8%8E%E8%AE%A1%E7%AE%97/03-%E6%B7%B1%E5%BA%A6%E5%AD%A6%E4%B9%A0%E8%AE%A1%E7%AE%97.md)
