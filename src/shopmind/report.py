"""报告生成模块。

职责：把 analyzer 算出来的结构化结果，整理成一段给大模型看的文本，
拼上系统提示词，调 llm，拿回一份"经营诊断报告"。

这里的核心不是代码，而是 **prompt 的设计**。关键原则：
1. 只把必要的数字喂给模型，不要丢整个 DataFrame（浪费 token 且容易出错）
2. 明确要求模型"只基于给定数据说话，不要编造"
3. 固定输出结构，让报告每次长得一样，便于对比和展示
"""
import sys
from pathlib import Path

import pandas as pd

# 直接把 report.py 当脚本运行时，需要把 src 加进模块搜索路径
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from shopmind.analyzer import collect_all  # noqa: E402
from shopmind.llm import LLMConfig, chat  # noqa: E402

# 系统提示词：定义模型扮演什么角色、遵守什么规矩
#
# 这几条约束是针对实测中的具体毛病加的：首版曾把波动的月度数据说成
# "1-8月销售额持续增长"，属于典型的小模型幻觉。约束要点是——
# 强制引用数字、用客观事实替代主观概括、禁止在数据不足时下结论。
SYSTEM_PROMPT = """你是一位电商店铺的经营分析顾问。你的任务是根据给定的数据，输出一份给店主的诊断报告。

必须严格遵守以下规则：
1. 只能使用我提供的数据，绝对不要编造任何数字或事实。
2. 每一句结论后面都要附上具体数字作为依据，格式如：（3月314单，环比+27.64%）。
3. 不准使用"持续增长""稳步上升""一路上涨"这类概括词。判断趋势必须以
   "环比上升月份数""环比下降月份数""最长连续同向变动"这三个已给出的指标为准。
   如果上升和下降的月份都存在，就必须如实描述为"波动"，并指出最高月和最低月。
4. 只做描述和归因，不要做预测，不要推算未提供的月份。
5. 如果某项数据没有提供，就明确说"数据未提供"，不要猜测。
6. 建议要具体可执行，避免"加强管理"这类空话，要落到具体品类、渠道、动作上。
7. 用简体中文，纯文本输出，不要用 Markdown 的星号或井号。

输出格式固定为以下四段，每段用方括号标题：
【本月整体表现】2-4 句，先给结论再给依据。
【售后问题归因】2-4 句，指出问题最严重的品类并给出排查方向。
【渠道效率对比】2-4 句，对比直播与店铺渠道并说明依据。
【行动建议】列出 3 条具体动作，每条一句话。"""


def _fmt_table(df: pd.DataFrame, title: str) -> str:
    """把 DataFrame 转成紧凑的文本表格，比 to_string() 省 token。"""
    return f"### {title}\n{df.to_string(index=False)}\n"


def build_data_brief(results: dict) -> str:
    """把分析结果拼成给模型的"数据简报"。

    两个原则：
    1. 只保留回答那三个问题所需的数据，不做全量倾倒（省 token，也少干扰）
    2. 把"已算好的结论性事实"单独列一段——模型只负责表达，不负责算术
    """
    parts = ["以下是我店铺的经营数据，请据此分析：\n"]

    s = results["整体概览"]
    parts.append(
        "### 整体概览\n"
        f"订单总数：{s['订单总数']}\n"
        f"成交总额：{s['成交总额']} 元\n"
        f"客单价：{s['客单价']} 元\n"
        f"换货率：{s['换货率']}%\n"
        f"退货率：{s['退货率']}%\n"
        f"评价率：{s['评价率']}%\n"
    )

    parts.append(_fmt_table(results["月度趋势"], "月度趋势（1-12月）"))

    facts = results.get("月度事实") or {}
    if facts:
        lines = "\n".join(f"{k}：{v}" for k, v in facts.items())
        parts.append(
            "### 月度趋势的客观事实（已由程序算好，请直接引用，不要自己重新判断）\n"
            f"{lines}\n"
        )

    parts.append(_fmt_table(results["品类售后"], "各品类售后情况"))
    parts.append(_fmt_table(results["渠道效率"], "各渠道对比"))

    parts.append(
        "\n请特别回答这三个问题：\n"
        "1. 全年的销售趋势是怎样的？请依据上面给出的客观事实判断，"
        "并引用最高月和最低月的数据。\n"
        "2. 哪个品类的售后问题最严重？店主应该从哪个方向去排查？\n"
        "3. 直播下单和店铺下单，哪个渠道的效率更高？依据是什么？"
    )
    return "\n".join(parts)


def generate_report(df: pd.DataFrame, config: LLMConfig | None = None) -> str:
    """完整流程：算分析 → 拼 prompt → 调模型 → 返回报告文本。"""
    results = collect_all(df)
    brief = build_data_brief(results)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": brief},
    ]
    return chat(messages, config)


if __name__ == "__main__":
    from shopmind.data_loader import load_clean

    provider = sys.argv[1] if len(sys.argv) > 1 else "local"
    data = load_clean()
    print(f"正在生成报告（provider={provider}）...\n")
    print(generate_report(data, LLMConfig(provider=provider)))
