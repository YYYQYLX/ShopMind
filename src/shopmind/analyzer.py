"""分析模块。

职责：所有"算数"的逻辑都在这里。每个函数只回答一个问题，返回结构化结果
（dict / DataFrame），不含任何画图和文字描述。这样上层既可以用它画图，
也可以把它喂给大模型生成报告。
"""
import pandas as pd


def overall_summary(df: pd.DataFrame) -> dict:
    """整体概览：订单量、成交总额、客单价、售后率。

    对应老板的第一个问题"这个月整体卖得怎么样"的基础数字。
    """
    n = len(df)
    gmv = df["成交金额"].sum()
    return {
        "订单总数": int(n),
        "成交总额": round(float(gmv), 2),
        "客单价": round(float(gmv / n), 2) if n else 0.0,
        "购买件数": int(df["购买数量"].sum()),
        "换货率": round(float(df["换货"].mean()) * 100, 2),
        "退货率": round(float(df["退货"].mean()) * 100, 2),
        "评价率": round(float(df["已评价"].mean()) * 100, 2),
        "独立用户数": int(df["用户ID"].nunique()),
    }


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """按月汇总：订单量、成交额、客单价。用于判断"跟其他月比是升是降"。

    返回的 DataFrame 按月份升序，列：月份 / 订单量 / 成交额 / 客单价。
    另外附加 环比订单增长 列（百分比，第一个月为空）。
    """
    g = df.groupby("交易月份").agg(
        订单量=("订单编号", "count"),
        成交额=("成交金额", "sum"),
    )
    g["客单价"] = (g["成交额"] / g["订单量"]).round(2)
    g["成交额"] = g["成交额"].round(2)
    g["环比订单增长"] = (g["订单量"].pct_change() * 100).round(2)
    return g.reset_index()


def category_aftersales(df: pd.DataFrame) -> pd.DataFrame:
    """按品类统计售后情况，用于定位"哪个品类问题最严重"。

    除了换货率/退货率，还给出该品类的订单量作为权重参考——
    一个只有 10 单的品类退货率高，未必比 1000 单的品类更值得关注。
    结果按退货率降序。
    """
    g = df.groupby("品类").agg(
        订单量=("订单编号", "count"),
        换货率=("换货", "mean"),
        退货率=("退货", "mean"),
        评价率=("已评价", "mean"),
        客单价=("成交金额", "mean"),
    )
    for col in ["换货率", "退货率", "评价率"]:
        g[col] = (g[col] * 100).round(2)
    g["客单价"] = g["客单价"].round(2)
    return g.sort_values("退货率", ascending=False).reset_index()


def channel_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    """对比直播下单与店铺下单的效率，对应第三个问题。

    效率这里拆成三个可量化的指标：客单价、购买件数、售后率。
    单看订单量只能说明"哪里来的人多"，不能说明"哪里的人更好"。
    """
    g = df.groupby("订单来源").agg(
        订单量=("订单编号", "count"),
        客单价=("成交金额", "mean"),
        平均件数=("购买数量", "mean"),
        换货率=("换货", "mean"),
        退货率=("退货", "mean"),
    )
    g["客单价"] = g["客单价"].round(2)
    g["平均件数"] = g["平均件数"].round(2)
    for col in ["换货率", "退货率"]:
        g[col] = (g[col] * 100).round(2)
    return g.reset_index()


def membership_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """会员与非会员对比，作为补充分析。"""
    g = df.groupby("是否会员").agg(
        订单量=("订单编号", "count"),
        客单价=("成交金额", "mean"),
        退货率=("退货", "mean"),
        评价率=("已评价", "mean"),
    )
    g["客单价"] = g["客单价"].round(2)
    for col in ["退货率", "评价率"]:
        g[col] = (g[col] * 100).round(2)
    g.index = g.index.map({True: "会员", False: "非会员"})
    return g.reset_index()


def monthly_facts(df: pd.DataFrame) -> dict:
    """把月度趋势提炼成"事实陈述"，直接喂给大模型。

    为什么要有这个函数：小模型的算术能力很弱，让它自己从表格里读环比、
    判断"是升是降"，它会凭印象编（比如把波动的数据说成"持续增长"）。
    正确做法是——**算术在代码里做完，模型只负责表达**。
    """
    trend = monthly_trend(df)
    counts = trend["订单量"].tolist()
    months = trend["交易月份"].tolist()
    if not counts:
        return {}

    peak_i = counts.index(max(counts))
    low_i = counts.index(min(counts))

    # 逐月对比，统计涨/跌的月份数（不看第 1 个月，它没有环比）
    up = down = 0
    for prev, cur in zip(counts, counts[1:]):
        if cur > prev:
            up += 1
        elif cur < prev:
            down += 1

    # 连续同向变动的最长段：判断"能不能说持续增长"的客观依据
    longest_run = 1
    cur_run = 1
    cur_dir = 0
    for prev, cur in zip(counts, counts[1:]):
        d = 1 if cur > prev else (-1 if cur < prev else 0)
        if d != 0 and d == cur_dir:
            cur_run += 1
            longest_run = max(longest_run, cur_run)
        else:
            cur_dir = d
            cur_run = 1

    first, last = counts[0], counts[-1]
    change = (last - first) / first * 100 if first else 0

    return {
        "订单量最高月份": f"{months[peak_i]}月（{counts[peak_i]}单）",
        "订单量最低月份": f"{months[low_i]}月（{counts[low_i]}单）",
        "全年平均订单量": round(sum(counts) / len(counts), 1),
        "环比上升月份数": up,
        "环比下降月份数": down,
        "最长连续同向变动": f"{longest_run} 个月",
        "首月对比末月变化": f"{change:+.2f}%",
        "是否呈单调上升": "否" if down > 0 else "是",
    }


def collect_all(df: pd.DataFrame) -> dict:
    """把上面所有分析结果打包成一个 dict，供报告模块和界面统一消费。"""
    return {
        "整体概览": overall_summary(df),
        "月度趋势": monthly_trend(df),
        "月度事实": monthly_facts(df),
        "品类售后": category_aftersales(df),
        "渠道效率": channel_efficiency(df),
        "会员对比": membership_comparison(df),
    }


if __name__ == "__main__":
    from shopmind.data_loader import load_clean

    data = load_clean()
    for name, result in collect_all(data).items():
        print(f"\n{'=' * 50}\n{name}\n{'=' * 50}")
        print(result.to_string() if hasattr(result, "to_string") else result)
