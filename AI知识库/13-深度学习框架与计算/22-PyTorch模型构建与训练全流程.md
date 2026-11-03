# PyTorch 模型构建与训练全流程：nn.Module、数据管道与训练循环

/> 来源：公开课程资料自学整理（更新于 2026-11-03）
> 一句话概括：一个 PyTorch 深度学习项目 = Dataset/DataLoader 数据管道 + nn.Module 模型 + 损失函数 + 优化器 + 可视化监控，五件套拼出训练循环。

## 核心概念

### 深度学习项目的五大模块
数据读取 → 网络设计 → 损失函数 → 梯度更新（优化器） → 辅助工具（保存/加载/可视化）。训练模型的本质就是**优化损失函数的过程**。

### nn.Module：一切网络的基类
- 自定义网络必须继承 `nn.Module`，遵守三条铁律：
  1. `__init__` 里**必须调用 `super().__init__()`**（父类会初始化存储训练中间变量的字典/集合，漏写报 `cannot assign parameters before Module.__init__() call`）；
  2. **需要学习的层放 `__init__`**（卷积层、Linear、`nn.Parameter`），**不需要学习参数的层放 `forward`**（BN、激活函数、Dropout）;
  3. **必须重写 `forward()`** 定义前向计算。
- Module 是 callable 的：`model(x)` 即执行 `forward`。
- **Module 可嵌套**：重复结构（残差块、Inception 块）抽成独立 Module 再组合，避免复制粘贴代码。
- `nn.Sequential` 是快速串联各层构建网络的捷径。
- `model.named_parameters()` 查看所有可训练参数；`model.state_dict()` 得到参数的有序字典（保存/加载用）。

### Dataset / DataLoader：数据管道
- **Dataset 是抽象类**，自定义数据集至少重写三个方法：`__init__`（读取与预处理）、`__len__`（数据集大小）、`__getitem__`（按下标返回一条数据+标签）。
- **DataLoader 是迭代器**，包住 Dataset，负责分 batch、shuffle、多进程加载（`num_workers`）。设计动机：数据太大不能一次性进内存，需要迭代式、多进程加载。
- Torchvision = 常用数据集 + 经典网络模型 + 常用图像处理方法三合一；`torchvision.datasets` 的接口本质都是 Dataset 的派生类，封装了下载→解压→解析全过程。
- 图片数据管道顺序：PIL Image → `transforms.ToTensor()` 转 Tensor → 各种变换/增强 → Normalize → DataLoader 出 batch。

## 关键方法/原理

### 损失函数怎么选
| 损失函数 | 适用场景 | 要点 |
|---|---|---|
| 0-1 损失 | 理论意义为主 | 导数恒为 0，无法用于梯度更新，实际几乎不用 |
| 平方损失 / MSE（L2） | 回归 | 最简单可导；系数 1/2 是为了求导后约掉 |
| MAE（L1） | 回归 | 对绝对误差，对离群点更鲁棒 |
| 交叉熵（CrossEntropyLoss） | 分类 | 衡量真实分布 p 与预测分布 q 的差距；`nn.CrossEntropyLoss` 已内置 LogSoftmax+NLLLoss，**网络末端不要再手动加 Softmax** |
| Softmax Loss | 多分类 | 交叉熵的特例：q 取 softmax 输出 |

- 概念辨析：损失函数 = 单样本误差；代价函数 = 全体样本误差的平均（经验风险）。实际混用不纠字眼。
- 拟合三态：**欠拟合**（没学到趋势）、**过拟合**（函数太复杂，死记训练点，新增本无法预测）、适度拟合是目标。损失并非越小越好——过小常意味着过拟合。

### 优化器与 batch size
- 三种梯度下降：**BGD**（全数据算完才更新，慢）、**SGD**（每条数据更新一次，快但受噪声影响）、**Mini-Batch**（折中，业界主流）。
- batch size 常取 2 的 n 次方（32/128/512），利于 GPU 并行。经验：**图像任务偏小，NLP 任务可大**。
- batch size 的权衡：大 → 梯度稳、训练稳，但显存吃紧、更新次数少、泛化差、易陷局部最优；小 → 更新频繁、带噪声反而易逃离局部最优、泛化好。

### 标准训练循环（必背模板）
```python
model = MyModel()
criterion = nn.CrossEntropyLoss()
optimizer = torch.optim.SGD(model.parameters(), lr=0.001, momentum=0.9)

for epoch in range(num_epochs):
    for inputs, labels in dataloader:
        optimizer.zero_grad()          # 梯度清零（不清会累加）
        outputs = model(inputs)        # 前向传播
        loss = criterion(outputs, labels)
        loss.backward()                # 反向传播，梯度写入 .grad
        optimizer.step()               # 用梯度更新参数
```

### 模型保存与加载两种方式
1. **只存参数**（推荐）：`torch.save(model.state_dict(), path)`；加载时先建网络结构再 `load_state_dict`。文件小、结构清晰。
2. **连结构一起存**：`torch.save(model, path)` / `torch.load(path)`；加载时无需重建网络，但跨版本/跨代码脆弱。

### 微调（finetune）的两种姿势
1. **冻结骨干只训头部**：加载预训练模型后 `param.requires_grad = False` 锁死全部参数，再替换/新增最后全连接层训练；
2. **全网络重训**：替换最后全连接层（输出数改成自己的类别数），以预训练权重为初始化，整个网络重新训练——**更常用**。
- 修改输出层的通用手法：`print(model)` 看结构，找到最后的 Linear，替换之。
- 微调三要素：数据必须是 3 通道 `(B, 3, H, W)`；用 ImageNet 的均值/方差归一化；resize 到模型推荐最小尺寸（如 224×224）。

### 训练可视化监控（TensorBoard）
- PyTorch ≥1.8 内置 `torch.utils.tensorboard.SummaryWriter`（更早版本需装 tensorboardX）。
- `add_scalar(tag, value, step)` 记 loss/accuracy/lr 曲线；`add_image` 记图像。启动 `tensorboard --logdir=runs`，浏览器看 6006 端口。
- 长训练必须挂曲线监控：loss 不再下降即可判定收敛、提前停。

## 经验与常见坑
- 忘记 `super().__init__()` → AttributeError；忘记 `zero_grad()` → loss 越训越怪。
- **训练/推理状态切换**：Dropout、BN 在训练与评估时行为不同，评估和上线前必须 `model.eval()`。
- 预训练模型下载慢/失败：手动下载权重文件后用 `load_state_dict` 本地加载。
- transforms 里 `Resize` 传 int 只缩放短边，后续 crop 可能裁掉大量信息；长宽比差异大的图要传 tuple。
- `CrossEntropyLoss` 内含 softmax，重复加 Softmax 层会让训练变慢变差。
- 数据集列表化预览（`list(dataset)`）在大数据集上会撑爆 Jupyter 的 IOPub 限额，仅小数据调试用。

## ⚠️ 时效性说明
- `models.alexnet(pretrained=True)` 的 `pretrained` 参数在新版 torchvision 已废弃，改用 `weights=` API。
- 迭代器取值：旧教程的 `.next()` 在 Python 3 需写成 `next(iterator)`。
- Torchvision 默认图像后端为 PIL，需安装 Pillow。
