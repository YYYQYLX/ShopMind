# ShopMind

本地跑的电商订单分析工具。读一份订单 CSV，算出经营指标并出图，再让本地部署的 Qwen 模型写一份中文诊断报告。有网页界面和命令行两种用法，不需要联网。

## 功能

- 数据清洗，派生成交金额、交易月份等字段
- 5 类分析：整体概览、月度趋势、品类售后、渠道效率、会员对比
- 出图 3 张
- 把分析结果交给本地模型，生成经营诊断报告
- 网页界面：上传 CSV、看指标和图、生成报告、针对数据追问

## 输出

![月度趋势](output/monthly_trend.png)

![品类售后](output/category_aftersales.png)

![渠道效率](output/channel_efficiency.png)

## 安装

需要 Python 3.10 以上，和一个提供 OpenAI 兼容接口的本地模型服务。我用的是 LM Studio。

```
pip install -r requirements.txt
```

下载模型，用的是 Qwen2.5-3B 的 Q4 量化版：

```
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen2.5-3B-Instruct-GGUF', local_dir='D:/models/Qwen25-3B-Q4', allow_patterns=['*q4_k_m*'])"
```

在 LM Studio 里把模型目录指到 `D:/models/Qwen25-3B-Q4`，加载模型，到「本地模型 API」页面把服务打开，默认地址 `http://localhost:1234/v1`。

## 使用

```
python main.py                        跑分析、出图
python src/shopmind/report.py local   调用本地模型生成报告
```

网页界面：

```
streamlit run app.py
```

跑起来后浏览器会自动打开 http://localhost:8501。左边可以换成自己上传的 CSV，也可以改模型名和接口地址。

模型 id 和代码里不一致时，用环境变量覆盖：

```
set SHOPMIND_MODEL=qwen2.5-3b-instruct
```

## 目录

```
app.py                     网页界面
main.py                    命令行入口
data/orders_raw.csv        订单数据（模拟生成）
output/                    图表输出
src/shopmind/
  data_loader.py           清洗
  analyzer.py              指标计算
  charts.py                画图
  llm.py                   模型调用
  report.py                提示词和报告生成
```

## 说明

`data/orders_raw.csv` 是 `numpy.random.seed(2023)` 生成的模拟数据，不是真实订单。

7B 模型在 8G 显存上加载会报 `failed to allocate buffer for kv cache`，默认上下文 16K 占的显存太多。换 3B 最省事，或者在 LM Studio 里把上下文长度限制到 2048。

模型会编趋势。第一版报告把波动的月度数据写成了「1-8 月销售额持续增长」，实际 2、4、8 月都在跌。现在环比数据先在代码里算好再交给模型，提示词里也禁止它使用「持续增长」这类词。
