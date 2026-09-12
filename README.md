# ShopMind — 本地化电商经营分析助手

上传订单数据，自动完成经营分析并**由本地部署的大模型生成中文诊断报告**。
全流程离线运行，不依赖任何云端 API，数据不出本机。

## 这个项目解决什么问题

中小电商店铺的订单数据里其实藏着很多经营信号——哪个品类售后率高、直播和店铺哪个渠道效率更高、销售波动是季节性还是异常。但这些数据通常只被用来对账，很少有人系统地把它转成经营判断。

ShopMind 做两件事：

1. **把数据算清楚**：清洗、分维度聚合、出图，产出可读的经营指标
2. **把数字讲成话**：把算好的指标交给本地大模型，生成一份店主能直接看懂的诊断报告

## 效果展示

| 月度订单量与成交额趋势 | 各品类售后率对比 |
|---|---|
| ![月度趋势](output/monthly_trend.png) | ![品类售后](output/category_aftersales.png) |

![渠道效率](output/channel_efficiency.png)

## 技术架构

```
订单 CSV
   │
   ▼
data_loader.py    清洗 + 派生字段（成交金额、月份、星期等）
   │
   ▼
analyzer.py       5 类分析：整体概览 / 月度趋势 / 品类售后 / 渠道效率 / 会员对比
   │
   ├──▶ charts.py      生成趋势图、售后对比图、渠道对比图
   │
   └──▶ report.py      拼装"数据简报"→ 调用本地大模型 → 诊断报告
             │
             ▼
        llm.py        OpenAI 兼容接口，本地与云端后端可切换
```

## 环境要求

- Python 3.10+
- 一个提供 OpenAI 兼容接口的本地模型服务（推荐 [LM Studio](https://lmstudio.ai/)）
- 显存 8G 及以下建议使用 3B 级模型的 Q4 量化版本

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备本地模型

下载模型（以 Qwen2.5-3B-Instruct 的 Q4 量化版本为例）：

```bash
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen2.5-3B-Instruct-GGUF', local_dir='D:/models/Qwen25-3B-Q4', allow_patterns=['*q4_k_m*'])"
```

在 LM Studio 中把模型目录指向该路径，加载模型，并在「本地模型 API」页面启动服务
（默认地址 `http://localhost:1234/v1`）。

### 3. 运行分析

```bash
python main.py
```

会打印关键经营指标，并在 `output/` 下生成 3 张图表。

### 4. 生成 AI 诊断报告

```bash
python src/shopmind/report.py local
```

模型名与前端不一致时，用环境变量覆盖，无需改代码：

```bash
set SHOPMIND_MODEL=qwen2.5-3b-instruct     # Windows
export SHOPMIND_MODEL=qwen2.5-3b-instruct  # macOS / Linux
```

## 关于数据

`data/orders_raw.csv` 是**模拟生成的示例数据**，用 `numpy.random.seed` 按预设分布造出，
用于验证整条分析链路，**不代表任何真实店铺的经营情况**。

换成真实数据时，只需保证 CSV 含以下字段即可：

`订单交易时间 / 订单编号 / 订单来源 / 用户ID / 会员 / 首次下单用户 / 性别 / 品类 / 商品单价 / 购买数量 / 活动优惠 / 换货 / 退货 / 已评价`

## 设计要点

**算术交给代码，表达交给模型。** 小模型的数值敏感度很弱，让它自己从表格里读环比、
判断趋势，它会倾向于讲一个顺畅的故事（实测中曾把波动数据说成"持续增长"）。
因此 `analyzer.monthly_facts()` 会把趋势判断所需的客观指标（环比升降月份数、
最长连续同向变动、最高/最低月）预先算好再交给模型，模型只负责组织语言。

**推理与呈现分离。** `analyzer.py` 只产出结构化数据，不画图也不写文案；
`charts.py` 和 `report.py` 各自消费这些数据。同一套分析结果既能出图也能喂给模型，
未来接 Web 界面也不用改分析逻辑。

**后端可切换。** `llm.py` 用同一套 HTTP 代码适配本地与云端，两者都遵循
OpenAI 的 `/chat/completions` 协议——这也是目前业界对接大模型的通用做法。

## 项目结构

```
ShopMind/
├── main.py                   命令行入口
├── requirements.txt
├── data/
│   └── orders_raw.csv        示例订单数据
├── output/                   图表输出目录
└── src/shopmind/
    ├── data_loader.py        加载与清洗
    ├── analyzer.py           经营指标计算
    ├── charts.py             图表生成
    ├── llm.py                大模型调用（本地/云端可切换）
    └── report.py             提示词与报告生成
```
