"""命令行入口。

用法（在项目根目录下）：
    python main.py

会依次跑完数据加载 → 分析 → 出图，并在终端打印关键结论。
第 2 周接入本地模型后，这里会再加一步"生成经营诊断报告"。
"""
import sys
from pathlib import Path

# 把 src 加入模块搜索路径，这样直接 `python main.py` 就能 import shopmind
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from shopmind.analyzer import collect_all  # noqa: E402
from shopmind.charts import render_all  # noqa: E402
from shopmind.data_loader import load_clean  # noqa: E402


def main() -> None:
    print("=" * 60)
    print("ShopMind — 电商经营分析")
    print("=" * 60)

    df = load_clean()
    print(f"\n[1/3] 数据加载完成：{len(df)} 条订单，{df['用户ID'].nunique()} 位用户")

    results = collect_all(df)
    print("\n[2/3] 分析完成。整体概览：")
    for k, v in results["整体概览"].items():
        print(f"    {k}: {v}")

    print("\n月度趋势：")
    print(results["月度趋势"].to_string(index=False))

    print("\n品类售后：")
    print(results["品类售后"].to_string(index=False))

    print("\n渠道效率：")
    print(results["渠道效率"].to_string(index=False))

    paths = render_all(df)
    print(f"\n[3/3] 已生成 {len(paths)} 张图表：")
    for p in paths:
        print(f"    {p}")


if __name__ == "__main__":
    main()
