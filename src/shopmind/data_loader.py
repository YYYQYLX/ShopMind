"""数据加载与预处理模块。

职责：把原始 CSV 读进来，清洗成后续分析能直接用的 DataFrame。
不涉及任何业务分析逻辑，只负责"把数据弄干净"。
"""
from pathlib import Path

import pandas as pd

# 项目中所有相对路径都以项目根目录为基准，避免依赖"当前工作目录"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


def load_raw(csv_path: str | Path | None = None) -> pd.DataFrame:
    """读取原始订单 CSV。

    默认读取 data/orders_raw.csv。返回的 DataFrame 保持原始字段，不做修改。
    """
    if csv_path is None:
        csv_path = DATA_DIR / "orders_raw.csv"
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    return df


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """清洗与派生字段。

    做三件事：
    1. 时间字段转 datetime，并派生 交易日期/交易月份/星期几
    2. 衍生 成交金额 = 商品单价 * 购买数量（原始数据没有这一列，但分析必然要用）
    3. 补齐 是否会员 / 是否首次下单 等布尔列，方便后续过滤

    返回新的 DataFrame，不修改入参。
    """
    out = df.copy()

    out["订单交易时间"] = pd.to_datetime(out["订单交易时间"])
    out["交易日期"] = out["订单交易时间"].dt.date
    out["交易月份"] = out["订单交易时间"].dt.month
    out["交易年份"] = out["订单交易时间"].dt.year
    out["星期几"] = out["订单交易时间"].dt.dayofweek  # 0 = 周一

    # 成交金额：这一列原始数据里没有，但"客单价"这类指标必须靠它
    out["成交金额"] = out["商品单价"] * out["购买数量"]

    # 把 是/否 转成布尔，过滤时比字符串比较直观
    out["是否会员"] = out["会员"] == "是"
    out["是否首次下单"] = out["首次下单用户"] == "是"
    out["是否直播下单"] = out["订单来源"] == "直播下单"

    return out


def load_clean(csv_path: str | Path | None = None) -> pd.DataFrame:
    """一步拿到清洗后的数据，供分析模块直接调用。"""
    return preprocess(load_raw(csv_path))


if __name__ == "__main__":
    # 直接运行本文件时可用来验证数据是否读得进来
    d = load_clean()
    print(f"数据规模: {d.shape[0]} 行 × {d.shape[1]} 列")
    print(f"时间范围: {d['订单交易时间'].min()} ~ {d['订单交易时间'].max()}")
    print(f"独立用户: {d['用户ID'].nunique()}")
    print(d.head(3).to_string())
