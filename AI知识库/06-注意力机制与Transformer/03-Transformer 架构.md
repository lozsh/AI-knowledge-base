# Transformer 架构

<p class="note-date">更新于 2026-11-03</p>

**一句话定义**：Transformer 是完全由注意力机制构成（不含循环和卷积）的编码器-解码器神经网络，是大语言模型的鼻祖与核心架构。

随着 NLP 从统计机器学习走向深度学习，文本表示方法也随之演进，但网络架构主要继承了从计算机视觉发展出的三类结构：前馈神经网络（FNN，层间全连接）、卷积神经网络（CNN，用少量卷积参数做特征提取）、循环神经网络（RNN，利用历史信息、含环与自重复）。由于 NLP 处理的是序列，擅长时序的 RNN 及其衍生架构 LSTM 长期是 NLP 的霸主（如开创预训练思想的 ELMo 就用双向 LSTM）。

但 RNN 有两个难以弥补的缺陷：一是**序列依序计算**，无法利用 GPU 并行，参数量不大却时间成本很高；二是**难以捕捉长距离依赖**，距离越远的关系越难学，LSTM 的门控只是部分缓解。Vaswani 等人（2017，《Attention Is All You Need》）参考最早在 CV 领域提出、常被融入 RNN 使用的注意力机制，搭建了完全由注意力构成的 Transformer，让注意力一跃成为深度学习最核心的架构之一。后续预训练语言模型基本是对其 Encoder/Decoder 部分的取舍与改进：只用 Encoder 的 BERT、只用 Decoder 的 GPT。

## 核心原理

### 注意力机制：从精确匹配到柔性加权

注意力机制的核心思想：关注一张图片或一段文本时，无需看清全部内容，只需把注意力集中在重点部分。它有三个核心变量——**Query（查询）、Key（键）、Value（真值）**。例如在新闻报道中找时间，Query 是"时间/日期"类的稠密向量，Key 和 Value 是整个文本；Query 与 Key 运算得到权重（每个 token 应分到的注意力大小），再与 Value 加权求和得到结果。

用字典查询理解公式的推导：普通字典只支持精确匹配（Query="apple" 直接命中 Key）；但 Query="fruit" 时应同时匹配 apple 和 banana、不匹配 chair——需要给各 Key 分配权重 {apple:0.6, banana:0.4, chair:0} 再组合 Value。权重怎么算？利用词向量的性质：语义相近的词向量点积大于 0，不相似则小于 0，于是用**点积**度量 Query 与各 Key 的相似度，经 softmax 归一化为和为 1 的注意力分数，再对 Value 加权求和。当维度 d 较大时，QK 的点积会很大，softmax 后差异悬殊、影响梯度稳定，因此做缩放，得到核心公式：

Attention(Q, K, V) = softmax(QKᵀ/√d_k)·V

核心代码只有几行：

```python
scores = torch.matmul(query, key.transpose(-2, -1)) / math.sqrt(d_k)
p_attn = scores.softmax(dim=-1)
return torch.matmul(p_attn, value), p_attn
```

### 自注意力、掩码自注意力与多头注意力

**自注意力（self-attention）**：经典注意力中 Q 来自一个序列、K/V 来自另一个序列（如 Decoder 中 Q 来自解码端、K/V 来自编码器输出）；而自注意力让 Q、K、V 都由**同一个输入**经不同参数矩阵变换得到，拟合序列内每个 token 对其他所有 token 的关系。代码上就是 `attention(x, x, x)`。

**掩码自注意力（masked self-attention）**：语言模型训练的任务是根据前文预测下一个 token（如【BOS】I like you【EOS】逐词补全）。串行地"先算 step 1 再算 step 2"就丢掉了并行优势。解决办法：把每一步的输入（前缀 + 【MASK】遮蔽后文）一起并行送入模型，用上三角掩码遮蔽未来信息。实现上生成一个上三角 -inf 矩阵，加到注意力分数上再 softmax，-inf 位置的权重即变 0：

```python
mask = torch.full((1, seq_len, seq_len), float("-inf"))
mask = torch.triu(mask, diagonal=1)          # 上三角为 -inf
scores = scores + mask[:, :seqlen, :seqlen]  # 遮蔽未来位置
scores = F.softmax(scores.float(), dim=-1)
```

**多头注意力（multi-head attention）**：一次注意力只能拟合一种相关关系。多头对同一语料并行做多次注意力计算，各自拟合不同层次的信息（论文实验显示不同头确实关注不同模式），结果拼接后经线性层输出。工程实现的关键技巧：用三个 `n_embd × n_embd` 的组合矩阵代替 n 组小参数矩阵（矩阵内积再拼接等价于拼接矩阵再内积），前向时 reshape + transpose 拆成 n 个头并行计算，输出再 transpose + contiguous + view 合并头、经 W_o 投影回残差流。

## 关键概念

### Encoder-Decoder 结构

Transformer 针对的是 **Seq2Seq** 任务：输入一个自然语言序列、输出另一个可能不等长的序列。几乎所有 NLP 任务都可视为 Seq2Seq（文本分类 = 输出长度为 1，词性标注 = 输出等长），机器翻译是典型代表。整体思路是编码-解码：**Encoder** 把输入序列编码成语义向量，**Decoder** 把编码结果解码成目标序列。原模型中 Encoder 和 Decoder 各由 6 个 Layer 组成，Encoder 顶层的编码结果输出给 Decoder 的每一层。

**Encoder Layer** = 多头自注意力 + 前馈网络，各配残差连接和层归一化。**Decoder Layer** 有三个子层：掩码自注意力（每个 token 只能看之前的位置）→ 多头注意力/交叉注意力（Q 来自上一层输出，K/V 来自 Encoder 输出）→ 前馈网络。

### 组成部件

| 部件 | 说明 |
|---|---|
| 前馈网络 FFN | 两个线性层夹一个 ReLU 激活，外加 Dropout 防过拟合；对每个位置独立变换 |
| 层归一化 LayerNorm | 把每层输入归一化到稳定分布。BatchNorm 按 mini-batch 统计均值方差，在 batch 小、变长序列（RNN 时间维度展开）场景下失效；LayerNorm 改为在**每个样本的所有维度**上统计，统计维度不同、公式相同，深度网络中更常用 |
| 残差连接 | 每个子层输出与输入相加（x + Attention(x) 后再归一化），允许最底层信息直达最高层，让高层专注学残差，避免深层模型退化 |
| Embedding 层 | 可训练的 (vocab_size, embedding_dim) 权重矩阵，本质是词表到向量的查找表；tokenizer 把文本切成 token 并转为 index，Embedding 查出 (batch_size, seq_len, embedding_dim) 的表示 |
| 位置编码 | 注意力对每个位置一视同仁，"我喜欢你"和"你喜欢我"完全相同；必须显式注入位置信息 |

### 位置编码（正余弦 / Sinusoidal）

原始 Transformer 用正余弦函数做绝对位置编码：偶数位置用 sin，奇数位置用 cos，分母随维度按 10000 的幂变化。两大好处：

1. **可外推**：公式可以算出训练集未见过的更长位置的编码；
2. **可表达相对位置**：PE(pos+k) 可由 PE(pos) 线性表示（sin(A+B)=sinA·cosB+cosA·sinB），固定间距 k 的相对关系易于学习。

数学上可严格推导：在两个位置 m、n 上对编码函数做泰勒展开，希望交叉项表达相对位置；将二维向量视为复数、用复数指数形式求解，得到二维解后按线性叠加性组合成偶数维编码；取频率底数为 10000（实验结果）使内积 ⟨p_m, p_n⟩ 随 |m−n| 增大有趋于零的趋势。

```python
pe = torch.zeros(block_size, n_embd)
div_term = torch.exp(torch.arange(0, n_embd, 2) * -(math.log(10000.0) / n_embd))
pe[:, 0::2] = torch.sin(position * div_term)
pe[:, 1::2] = torch.cos(position * div_term)
x = x + self.pe[:, :x.size(1)]   # 加到词向量上
```

### 完整模型

数据流：输入 idx → Embedding → 位置编码 → Dropout → Encoder（N 层）→ Decoder（N 层，接收 enc_out）→ 线性层 lm_head（映射到词表大小）→ 训练时经 softmax 与 targets 算交叉熵，推理时只取序列最后一个位置的 logits。工程上还需参数量统计（get_num_params）与权重初始化（线性层/Embedding 用 std=0.02 的正态分布）。

## 经验与常见坑

- **多头维度必须整除**：n_embd 必须是头数的整数倍，否则无法均匀拆分；每头维度 = dim / n_heads，缩放时除的也是 head_dim 而非总维度。
- **transpose 后不能直接 view**：PyTorch 的 view 基于底层连续存储，transpose 不改变存储，需要先 `.contiguous()` 再 view，否则报错。
- **掩码维度**：多头注意力的 mask 比单头多一个维度，形状为 (1, 1, seq_len, seq_len)，通过广播作用于所有 batch 和头；计算时按实际 seqlen 截取（序列可能短于 max_seq_len）。
- **softmax 前先转 float**：混合精度训练下 `scores.float()` 再 softmax 更稳定。
- **不要省略缩放 √d_k**：维度大时点积值差异悬殊，softmax 饱和导致梯度不稳定。

## ⚠️ 时效性说明

- 原始 Transformer 的 Post-LN（层归一化放在子层之后）在深层网络中训练不稳定，现代大模型（GPT、Llama 系列）普遍改用 Pre-LN；原始架构中 Encoder/Decoder 各 6 层、正余弦位置编码，也分别被更深层数和 RoPE 等方案取代。
- 本篇的实现是教学用"手搓"版本；生产环境中应使用框架实现（如 PyTorch 官方 `nn.MultiheadAttention`、FlashAttention 等），并注意 KV 缓存等推理优化。

## 参见
- [注意力机制](01-%E6%B3%A8%E6%84%8F%E5%8A%9B%E6%9C%BA%E5%88%B6.md)：注意力评分函数、Bahdanau 注意力等基础机制
- [注意力引爆大模型的引擎](02-%E6%B3%A8%E6%84%8F%E5%8A%9B%E5%BC%95%E7%88%86%E5%A4%A7%E6%A8%A1%E5%9E%8B%E7%9A%84%E5%BC%95%E6%93%8E.md)：注意力如何演化为大模型引擎的宏观视角
- [大语言模型 · 大模型架构原理与演进](../07-%E5%A4%A7%E8%AF%AD%E8%A8%80%E6%A8%A1%E5%9E%8B/31-%E5%A4%A7%E6%A8%A1%E5%9E%8B%E6%9E%B6%E6%9E%84%E5%8E%9F%E7%90%86%E4%B8%8E%E6%BC%94%E8%BF%9B.md)：从 Transformer 到现代大模型架构的演进
- [大语言模型 · 预训练语言模型](../07-%E5%A4%A7%E8%AF%AD%E8%A8%80%E6%A8%A1%E5%9E%8B/02-%E9%A2%84%E8%AE%AD%E7%BB%83%E8%AF%AD%E8%A8%80%E6%A8%A1%E5%9E%8B.md)：基于 Transformer 的 BERT/GPT 等预训练模型
- [神经网络基础 · 网络架构](../03-%E7%A5%9E%E7%BB%8F%E7%BD%91%E7%BB%9C%E5%9F%BA%E7%A1%80/05-%E7%BD%91%E7%BB%9C%E6%9E%B6%E6%9E%84.md)：FNN/CNN/RNN 等基础网络架构