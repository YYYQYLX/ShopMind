"""ShopMind 的网页界面。

用法（在项目根目录下）：
    streamlit run app.py

左边选数据源和模型，中间看指标和图，下面让本地模型写诊断报告或回答具体问题。
"""
import sys
from io import BytesIO
from pathlib import Path

import streamlit as st

# 直接 `streamlit run app.py` 时，src 不在搜索路径里
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from shopmind.analyzer import collect_all  # noqa: E402
from shopmind.charts import render_all  # noqa: E402
from shopmind.data_loader import load_clean  # noqa: E402
from shopmind.llm import PROVIDERS, LLMConfig, chat  # noqa: E402
from shopmind.report import SYSTEM_PROMPT, answer_question, build_data_brief  # noqa: E402

st.set_page_config(page_title="ShopMind 经营分析", layout="wide")


@st.cache_data(show_spinner=False)
def load_data(csv_bytes: bytes | None):
    """读入并清洗数据。上传的文件按内容缓存，避免每次点击都重新解析。"""
    if csv_bytes is None:
        return load_clean()
    return load_clean(BytesIO(csv_bytes))


@st.cache_data(show_spinner="正在计算指标并出图...")
def analyze(csv_bytes: bytes | None):
    """跑完所有分析和图表，返回 (分析结果, 图片路径列表)。"""
    df = load_data(csv_bytes)
    results = collect_all(df)
    charts = [str(p) for p in render_all(df)]
    return results, charts


@st.cache_data(show_spinner=False)
def data_preview(csv_bytes: bytes | None):
    return load_data(csv_bytes)


def ask(messages: list[dict], cfg: LLMConfig) -> str:
    """统一的模型调用入口，把异常转成界面上能看懂的提示。"""
    try:
        return chat(messages, cfg)
    except Exception as e:  # noqa: BLE001 - 界面层要兜住所有异常，不能让页面崩掉
        st.error(
            f"调用模型失败：{e}\n\n"
            "本地模式请确认：LM Studio 已打开、模型已加载、"
            "「本地模型 API」页面的服务开关是打开的。"
        )
        return ""


# ---------------------------------------------------------------- 侧边栏

with st.sidebar:
    st.header("数据")
    uploaded = st.file_uploader("上传订单 CSV", type=["csv"])
    st.caption("不上传就用项目自带的模拟数据")

    st.divider()
    st.header("模型")
    provider = st.selectbox("后端", list(PROVIDERS), index=0)
    model = st.text_input("模型名", value=PROVIDERS[provider]["model"])
    base_url = st.text_input("接口地址", value=PROVIDERS[provider]["base_url"])
    st.caption("本地模式需要先启动 LM Studio 的服务，默认 1234 端口")

csv_bytes = uploaded.getvalue() if uploaded is not None else None

# ---------------------------------------------------------------- 主区域

st.title("ShopMind")
st.write("上传订单数据，看各项经营指标，再让本地跑的模型写一份诊断报告。")

results, chart_paths = analyze(csv_bytes)
df = data_preview(csv_bytes)

s = results["整体概览"]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("订单总数", f"{s['订单总数']:,}")
c2.metric("成交总额", f"{s['成交总额']:,.0f} 元")
c3.metric("客单价", f"{s['客单价']:.2f} 元")
c4.metric("退货率", f"{s['退货率']}%")
c5.metric("换货率", f"{s['换货率']}%")

st.divider()

tab_trend, tab_category, tab_channel, tab_member = st.tabs(
    ["月度趋势", "品类售后", "渠道效率", "会员对比"]
)

with tab_trend:
    st.image(chart_paths[0])
    st.dataframe(results["月度趋势"], hide_index=True)

with tab_category:
    st.image(chart_paths[1])
    st.dataframe(results["品类售后"], hide_index=True)

with tab_channel:
    st.image(chart_paths[2])
    st.dataframe(results["渠道效率"], hide_index=True)

with tab_member:
    st.dataframe(results["会员对比"], hide_index=True)

with st.expander("数据预览（前 20 行）"):
    st.dataframe(df.head(20), hide_index=True)

# ---------------------------------------------------------------- 报告与追问

st.divider()
st.subheader("AI 诊断报告")

cfg = LLMConfig(provider=provider, model=model, base_url=base_url)
brief = build_data_brief(results)

if st.button("生成报告", type="primary"):
    with st.spinner("模型正在读数据并组织语言，第一次调用要加载模型，可能要等几十秒"):
        text = ask(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": brief},
            ],
            cfg,
        )
    if text:
        st.session_state["report"] = text

if st.session_state.get("report"):
    # 报告是纯文本，换行要转成空行，Markdown 才会分段显示
    st.markdown(st.session_state["report"].replace("\n", "\n\n"))
    st.download_button(
        "下载报告",
        st.session_state["report"],
        file_name="shopmind_report.txt",
        mime="text/plain",
    )

st.subheader("追问")
question = st.text_input("针对这份数据问一个问题，比如：哪个品类的客单价最高？")

if st.button("提问"):
    if not question.strip():
        st.warning("先写一个问题")
    else:
        with st.spinner("模型正在回答"):
            try:
                answer = answer_question(results, question, cfg)
            except Exception as e:  # noqa: BLE001 - 界面层兜住异常，别让页面崩
                st.error(f"调用模型失败：{e}")
                answer = ""
        if answer:
            st.session_state["answer"] = (question, answer)

if st.session_state.get("answer"):
    q, a = st.session_state["answer"]
    st.markdown(f"**问：{q}**")
    st.markdown(a.replace("\n", "\n\n"))
