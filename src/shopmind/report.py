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
3. 不准使用"持续增长""稳步上升""一路上涨"这类概括词。趋势怎么写，以
   【月度趋势的客观事实】里的"趋势结论"为准，逐月升降以"环比上升的月份"
   和"环比下降的月份"为准，直接照抄，不要自己看表格重新判断。
4. 涉及排名、最高、最低、哪个更好这类判断，一律采用【客观事实】里给出的结论。
   同一段里不要把不同指标的最高值混为一谈（比如退货率最高的品类和换货率最高的
   品类可能不是同一个）。
5. 只做描述和归因，不要做预测，不要推算未提供的月份。
6. 如果某项数据没有提供，就明确说"数据未提供"，不要猜测。
7. 建议要具体可执行。每条都点名一个具体的品类或渠道，并带上支撑它的数字，
   比如：针对数码品类 5.88% 的退货率，逐条核对商品详情页的规格描述和实物是否一致。
   不要写"加强管理""优化体验""继续保持优势""制定改进措施"这类没有落点的空话。
8. 报告里的每个数字，都要原样照抄，不要自己换算、不要改变数字和名称的对应关系。
   所有"最高""最低""更优""基本持平"这类判断都已经算好给你了，直接引用，
   不要自己再去比较明细里的数字。写"某品类换货率 X%"时，X 必须是那个品类的
   换货率，不能拿它的退货率来顶。
9. 只输出报告正文。下面这些格式说明是给你看的，不要抄进报告，也不要复述。
10. 用简体中文，纯文本输出，不要用 Markdown 的星号或井号。

报告分四段，每段以方括号标题开头，每段不少于两句话，四段都要写：
【整体表现】先说全年是升、是降还是波动，再给依据，并指出最高月和最低月。
【售后问题归因】先说退货率最高的品类，再说换货率最高的品类，最后给排查方向。
【渠道效率对比】先对比两个渠道的客单价和平均件数，再对比退货率，最后给结论。
【行动建议】三条，每条一句话。这一段最容易漏，不要漏。"""


def _fmt_months(df: pd.DataFrame) -> str:
    """月度趋势：一行一个月，环比直接贴在订单量后面。

    一开始这里给的是表格（交易月份/订单量/成交额/客单价/环比…），结果模型
    把行看串了，写出"2月305单"（305 实际是 1 月）。数值和它的标签挨在一起
    之后，这类错位就没了——**给模型的数据，别让它自己去对齐列**。
    """
    lines = []
    for _, r in df.iterrows():
        pct = r["环比订单增长"]
        tail = "" if pd.isna(pct) else f"（环比{pct:+.2f}%）"
        lines.append(f"{int(r['交易月份'])}月 {int(r['订单量'])}单{tail}")
    return "### 月度趋势（每行一个月）\n" + "\n".join(lines) + "\n"


def _fmt_categories(df: pd.DataFrame) -> str:
    """各品类售后：每行一个品类，指标名和数值成对出现。

    表格形式下模型抓错过列——把家居的退货率 5.09% 说成了它的换货率。
    """
    lines = []
    for _, r in df.iterrows():
        lines.append(
            f"{r['品类']} 退货率{r['退货率']}% 换货率{r['换货率']}% "
            f"客单价{r['客单价']}元 {int(r['订单量'])}单"
        )
    return "### 各品类售后情况（每行一个品类）\n" + "\n".join(lines) + "\n"


def _fmt_channels(df: pd.DataFrame) -> str:
    """各渠道对比：同上，每个指标都带着自己的名字。"""
    lines = []
    for _, r in df.iterrows():
        lines.append(
            f"{r['订单来源']} {int(r['订单量'])}单 客单价{r['客单价']}元 "
            f"平均{r['平均件数']}件 退货率{r['退货率']}% 换货率{r['换货率']}%"
        )
    return "### 各渠道对比（每行一个渠道）\n" + "\n".join(lines) + "\n"


def _fmt_conclusions(results: dict) -> str:
    """把三个问题的结论拼成一段，紧挨着提问放。

    为什么要有这一段：小模型即使拿到了"换货率最高的是家居"，也会自己再比一遍
    表格，然后写成"换货率最高的也是数码"。所以判断类的结论统一由代码给出，
    而且放在最靠近提问的位置——位置越近，它越倾向于照抄。
    """
    m = results.get("月度事实") or {}
    c = results.get("品类事实") or {}
    ch = results.get("渠道事实") or {}

    out = ["### 下面几句是已经算好的结论，直接引用，数字一个字都不要改"]

    if m:
        out.append(
            "趋势："
            f"{m['趋势结论']}。环比上升的月份是{m['环比上升的月份']}，"
            f"环比下降的月份是{m['环比下降的月份']}；"
            f"最高月{m['订单量最高月份']}，最低月{m['订单量最低月份']}，"
            f"月均{m['全年平均订单量']}单。"
        )
    if c:
        out.append(
            f"售后：退货率最高的是{c['退货率最高的品类']}；"
            f"换货率最高的是{c['换货率最高的品类']}。"
        )
    if ch:
        out.append(
            f"渠道：{ch['渠道结论']}"
            f"（{ch['客单价']}；{ch['平均件数']}；{ch['退货率']}）"
        )
    return "\n".join(out) + "\n"


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

    parts.append(_fmt_months(results["月度趋势"]))
    parts.append(_fmt_categories(results["品类售后"]))
    parts.append(_fmt_channels(results["渠道效率"]))
    parts.append(_fmt_conclusions(results))

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
