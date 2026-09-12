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

    # 逐月升降明细，直接写成"哪几个月升、哪几个月降"。
    # 只给汇总数字（上升 4 个、下降 7 个）不够——模型想说具体月份时还是会凭印象编，
    # 这就是首版说出"1-4 月增长显著"的原因（实际 2 月是跌的）。
    ups, downs = [], []
    for m, prev, cur in zip(months[1:], counts, counts[1:]):
        if cur > prev:
            ups.append(f"{m}月")
        elif cur < prev:
            downs.append(f"{m}月")

    return {
        "订单量最高月份": f"{months[peak_i]}月（{counts[peak_i]}单）",
        "订单量最低月份": f"{months[low_i]}月（{counts[low_i]}单）",
        "全年平均订单量": round(sum(counts) / len(counts), 1),
        "环比上升的月份": "、".join(ups) if ups else "无",
        "环比下降的月份": "、".join(downs) if downs else "无",
        "环比上升月份数": up,
        "环比下降月份数": down,
        "最长连续同向变动": f"{longest_run} 个月",
        "首月对比末月变化": f"{change:+.2f}%",
        "是否呈单调上升": "否" if down > 0 else "是",
        "趋势结论": (
            "各月有升有降，整体是波动，不存在持续上升或持续下降"
            if up and down
            else "全年基本单调上升" if up else "全年基本单调下降"
        ),
    }


def category_facts(df: pd.DataFrame) -> dict:
    """品类售后的客观事实。

    同样是为了替模型做判断：让它从四行表格里挑出"退货率最高的品类"，
    它会挑错——实测中它把换货率最高的也说成了退货率最高的那个品类。
    与其反复叮嘱，不如直接把结论算好。
    """
    t = category_aftersales(df)
    if t.empty:
        return {}

    worst_return = t.loc[t["退货率"].idxmax()]
    worst_exchange = t.loc[t["换货率"].idxmax()]
    best_return = t.loc[t["退货率"].idxmin()]

    return {
        "退货率最高的品类": (
            f"{worst_return['品类']}（退货率 {worst_return['退货率']}%，"
            f"换货率 {worst_return['换货率']}%，{int(worst_return['订单量'])} 单）"
        ),
        "换货率最高的品类": (
            f"{worst_exchange['品类']}（换货率 {worst_exchange['换货率']}%，"
            f"退货率 {worst_exchange['退货率']}%，{int(worst_exchange['订单量'])} 单）"
        ),
        "退货率最低的品类": f"{best_return['品类']}（{best_return['退货率']}%）",
        "注意": "退货率最高和换货率最高的不是同一个品类，回答时不要合并成一个。",
    }


def channel_facts(df: pd.DataFrame) -> dict:
    """渠道对比的客观事实。

    这里要防的是另一种误判：把"订单量更大"直接说成"效率更高"。
    订单量只说明人从哪来，效率要看客单价、件数和售后率。
    """
    t = channel_efficiency(df).set_index("订单来源")
    if not {"直播下单", "店铺下单"}.issubset(t.index):
        return {}

    live, shop = t.loc["直播下单"], t.loc["店铺下单"]

    def _compare(col: str, unit: str, lower_is_better: bool = False) -> str:
        """对比同一指标在两个渠道上的表现。

        相对差小于 1% 时统一说"基本持平"——否则 150.48 和 150.24 这种
        0.16% 的差距会被标成"直播更优"，模型很可能会把它当成一条结论写进报告。
        """
        a, b = float(live[col]), float(shop[col])
        base = max(abs(a), abs(b))
        if base and abs(a - b) / base < 0.01:
            return f"{col}：直播 {a}{unit}、店铺 {b}{unit}，基本持平"
        winner = "直播" if ((a < b) if lower_is_better else (a > b)) else "店铺"
        return f"{col}：直播 {a}{unit}、店铺 {b}{unit}，差 {round(abs(a - b), 2)}{unit}，{winner}更优"

    price_gap_pct = abs(float(live["客单价"]) - float(shop["客单价"])) / float(shop["客单价"]) * 100

    return {
        "订单量": f"直播 {int(live['订单量'])} 单，店铺 {int(shop['订单量'])} 单",
        "客单价": _compare("客单价", " 元"),
        "平均件数": _compare("平均件数", " 件"),
        "退货率": _compare("退货率", "%", lower_is_better=True),
        "换货率": _compare("换货率", "%", lower_is_better=True),
        "客单价差异幅度": f"{round(price_gap_pct, 2)}%",
        "渠道结论": (
            f"两渠道客单价差异仅 {round(price_gap_pct, 2)}%，平均件数几乎相同，"
            f"差别主要在退货率（直播 {live['退货率']}% 低于店铺 {shop['退货率']}%）。"
            "订单量上直播更多，但那属于销量差异，不等于单位用户质量更高。"
        ),
    }


def collect_all(df: pd.DataFrame) -> dict:
    """把上面所有分析结果打包成一个 dict，供报告模块和界面统一消费。"""
    return {
        "整体概览": overall_summary(df),
        "月度趋势": monthly_trend(df),
        "月度事实": monthly_facts(df),
        "品类售后": category_aftersales(df),
        "品类事实": category_facts(df),
        "渠道效率": channel_efficiency(df),
        "渠道事实": channel_facts(df),
        "会员对比": membership_comparison(df),
    }


if __name__ == "__main__":
    from shopmind.data_loader import load_clean

    data = load_clean()
    for name, result in collect_all(data).items():
        print(f"\n{'=' * 50}\n{name}\n{'=' * 50}")
        print(result.to_string() if hasattr(result, "to_string") else result)
