"""大模型调用模块。

设计成"可切换后端"：
- provider="local"  → 调用本地 LM Studio / Ollama 的 OpenAI 兼容接口
- provider="cloud"  → 调用智谱 Z.ai 的开放平台接口

两者都遵循 OpenAI 的 /chat/completions 协议，所以底层用同一套 HTTP 代码，
只是 base_url 和模型名不同。这也是为什么这个模块能写成可切换的——
**接口协议一致**是当前业界主流做法，值得记住这个点。
"""
import json
import os
from dataclasses import dataclass, field

import requests

# 后端配置。改这里就能切换本地/云端，不用动其他代码。
#
# 本地模型有多个可选时，用环境变量 SHOPMIND_MODEL 覆盖，不必改代码：
#   set SHOPMIND_MODEL=qwen2.5-3b-instruct
# 调试阶段推荐 3B（快、稳）；最终演示可用 7B（效果更好，但需限制上下文）：
#   lms load qwen2.5-7b-instruct -c 2048 --gpu max
PROVIDERS = {
    "local": {
        "base_url": "http://localhost:1234/v1",  # LM Studio / Bionic 默认的本地服务地址
        # 必须和 LM Studio / Bionic 里实际加载的模型 id 完全一致。
        # 默认用 3B：8G 显存跑 3B 很轻松，7B 会因为 KV cache 分配失败而加载不了。
        # 显存够大时换成 7B 效果更好，改这里或用环境变量都行。
        "model": "qwen2.5-3b-instruct",
        "api_key": "lm-studio",  # 本地服务不校验，随便填一个非空值
    },
    "cloud": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        # 云端必须有真实 key。优先读环境变量，避免把密钥写进代码：
        #   在 cmd 里执行  set ZHIPU_API_KEY=你的key
        "api_key": os.environ.get("ZHIPU_API_KEY", ""),
    },
}

# 允许用环境变量临时覆盖本地模型名，方便在 3B / 7B 之间切换
_ENV_MODEL = os.environ.get("SHOPMIND_MODEL")
if _ENV_MODEL:
    PROVIDERS["local"]["model"] = _ENV_MODEL


@dataclass
class LLMConfig:
    provider: str = "local"
    temperature: float = 0.3
    timeout: int = 120
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        cfg = PROVIDERS.get(self.provider)
        if cfg is None:
            raise ValueError(f"未知的 provider: {self.provider}，可选 {list(PROVIDERS)}")
        self.base_url = self.base_url or cfg["base_url"]
        self.model = self.model or cfg["model"]
        self.api_key = self.api_key or cfg["api_key"]


def chat(messages: list[dict], config: LLMConfig | None = None) -> str:
    """发一轮对话，返回模型回复的纯文本。

    messages 是标准的 OpenAI 格式：[{"role": "system"/"user"/"assistant", "content": "..."}]
    """
    config = config or LLMConfig()

    if not config.api_key:
        raise RuntimeError(
            f"provider={config.provider} 缺少 api_key。"
            "本地模式请确认 LM Studio 服务已启动；云端模式请先设置 ZHIPU_API_KEY 环境变量。"
        )

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "stream": False,
        "max_tokens": 2048,
    }

    resp = requests.post(
        f"{config.base_url.rstrip('/')}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        json=payload,
        timeout=config.timeout,
    )

    # 出问题时把服务端返回的原文带出来，比一句 "400 Bad Request" 有用得多
    if resp.status_code >= 400:
        raise RuntimeError(
            f"HTTP {resp.status_code} 调用失败。\n"
            f"请求地址: {config.base_url}/chat/completions\n"
            f"请求体: {json.dumps(payload, ensure_ascii=False)[:500]}\n"
            f"服务端返回: {resp.text[:800]}"
        )

    data = resp.json()
    return data["choices"][0]["message"]["content"]


def check_available(config: LLMConfig | None = None) -> tuple[bool, str]:
    """探活：看看配置的后端到底能不能用。

    返回 (是否可用, 说明文字)。在写正式逻辑前先跑这个，能省很多排查时间。
    """
    config = config or LLMConfig()
    try:
        reply = chat([{"role": "user", "content": "只回复两个字：可用"}], config)
        return True, f"[{config.provider}] {config.model} 可用，回复：{reply.strip()[:50]}"
    except Exception as e:  # noqa: BLE001 - 探活就是要吞掉所有异常并如实报告
        return False, f"[{config.provider}] 连接失败：{type(e).__name__}: {e}"


if __name__ == "__main__":
    import sys

    provider = sys.argv[1] if len(sys.argv) > 1 else "local"
    ok, msg = check_available(LLMConfig(provider=provider))
    print(("✅ " if ok else "❌ ") + msg)
    if not ok and provider == "local":
        print(
            "\n排查提示：\n"
            "  1. LM Studio 是否已打开？\n"
            "  2. 左侧 'Developer' 页签里，是否把 Server 打开了？(默认端口 1234)\n"
            "  3. 模型是否已加载进内存？"
        )
