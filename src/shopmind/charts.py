"""图表模块。

职责：只负责画图，不负责算数（数据从 analyzer 传入）。
所有图统一保存到 output/ 目录，返回生成的文件路径列表，
方便上层（界面 / 报告）引用。
"""
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from shopmind.analyzer import collect_all

# 用非交互后端，避免在没有屏幕的环境（比如之后部署）里报错
matplotlib.use("Agg")

# 中文字体：Windows 上 SimHei / 微软雅黑都可，Linux 部署时需换成 Noto Sans CJK
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"


def _save(fig, name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_monthly_trend(monthly: pd.DataFrame) -> Path:
    """月度订单量与成交额趋势（双轴）。回答"比上个月升了还是降了"。"""
    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    ax1.bar(monthly["交易月份"], monthly["订单量"], color="#74B9FF", alpha=0.85, label="订单量")
    ax1.set_xlabel("月份")
    ax1.set_ylabel("订单量", color="#2d6cdf")
    ax1.set_xticks(range(1, 13))

    ax2 = ax1.twinx()
    ax2.plot(monthly["交易月份"], monthly["成交额"], color="#E17055", marker="o", lw=2, label="成交额")
    ax2.set_ylabel("成交额（元）", color="#E17055")

    plt.title("月度订单量与成交额趋势")
    fig.tight_layout()
    return _save(fig, "monthly_trend.png")


def plot_category_aftersales(cat: pd.DataFrame) -> Path:
    """各品类换货率与退货率对比。回答"哪个品类售后问题最严重"。"""
    x = range(len(cat))
    fig, ax = plt.subplots(figsize=(9, 4.5))
    w = 0.36
    b1 = ax.bar([i - w / 2 for i in x], cat["换货率"], w, label="换货率(%)", color="#FF6B6B")
    b2 = ax.bar([i + w / 2 for i in x], cat["退货率"], w, label="退货率(%)", color="#4ECDC4")
    ax.set_xticks(list(x))
    ax.set_xticklabels(cat["品类"])
    ax.set_ylabel("比例（%）")
    ax.legend()
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h, f"{h:.1f}", ha="center", va="bottom", fontsize=9)
    plt.title("各品类售后率对比")
    fig.tight_layout()
    return _save(fig, "category_aftersales.png")


def plot_channel(channel: pd.DataFrame) -> Path:
    """渠道效率对比：客单价 + 退货率。回答"直播还是店铺更值得投"。"""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    colors = ["#45B7D1", "#FFA07A"]

    axes[0].bar(channel["订单来源"], channel["客单价"], color=colors)
    axes[0].set_title("各渠道客单价（元）")
    for i, v in enumerate(channel["客单价"]):
        axes[0].text(i, v, f"{v:.0f}", ha="center", va="bottom")

    axes[1].bar(channel["订单来源"], channel["退货率"], color=colors)
    axes[1].set_title("各渠道退货率（%）")
    for i, v in enumerate(channel["退货率"]):
        axes[1].text(i, v, f"{v:.1f}", ha="center", va="bottom")

    fig.tight_layout()
    return _save(fig, "channel_efficiency.png")


def render_all(df: pd.DataFrame) -> list[Path]:
    """一次生成全部图表，返回文件路径列表。"""
    results = collect_all(df)
    return [
        plot_monthly_trend(results["月度趋势"]),
        plot_category_aftersales(results["品类售后"]),
        plot_channel(results["渠道效率"]),
    ]


if __name__ == "__main__":
    from shopmind.data_loader import load_clean

    for p in render_all(load_clean()):
        print(f"已生成: {p}")
