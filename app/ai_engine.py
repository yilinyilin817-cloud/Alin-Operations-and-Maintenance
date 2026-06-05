"""
AI 智能引擎模块
支持本地 Ollama 和云端 API 的一键切换
支持第三方服务商模型自动获取、API Key 持久化
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional, List, Dict

from PySide6.QtCore import QThread, Signal


# ---- 配置文件路径 ----
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".aiinlink")
CONFIG_FILE = os.path.join(CONFIG_DIR, "providers.json")


# ---- 系统提示词 ----
SYSTEM_PROMPT = """你是一个专业的网络与服务器诊断助手 AiinLink。
你的职责是：
1. 分析用户提供的终端输出、网络探测结果，诊断问题原因
2. 给出具体的排障建议和修复命令
3. 当用户输入不完整的命令时，预测并补全命令

回答要求：
- 使用中文回答
- 给出具体的命令时，用代码块包裹
- 诊断报告使用 Markdown 格式
- 简洁明了，直击要害
"""


# ---- 预设服务商配置 ----
PRESET_PROVIDERS = {
    "ollama": {
        "name": "Ollama (本地)",
        "type": "ollama",
        "base_url": "http://localhost:11434",
        "api_key": "",
        "model": "qwen2.5:7b",
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
    },
    "deepseek": {
        "name": "DeepSeek",
        "type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
    },
    "zhipu": {
        "name": "智谱 AI (GLM)",
        "type": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "",
        "model": "glm-4-flash",
    },
    "moonshot": {
        "name": "Moonshot (月之暗面)",
        "type": "openai_compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key": "",
        "model": "moonshot-v1-8k",
    },
    "qwen": {
        "name": "通义千问 (阿里云)",
        "type": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "",
        "model": "qwen-turbo",
    },
    "siliconflow": {
        "name": "SiliconFlow (硅基流动)",
        "type": "openai_compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "gemini": {
        "name": "Google Gemini",
        "type": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key": "",
        "model": "gemini-2.0-flash",
    },
    "baichuan": {
        "name": "百川智能",
        "type": "openai_compatible",
        "base_url": "https://api.baichuan-ai.com/v1",
        "api_key": "",
        "model": "Baichuan4",
    },
    "minimax": {
        "name": "MiniMax",
        "type": "openai_compatible",
        "base_url": "https://api.minimax.chat/v1",
        "api_key": "",
        "model": "MiniMax-Text-01",
    },
    "yi": {
        "name": "零一万物 (Yi)",
        "type": "openai_compatible",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "api_key": "",
        "model": "yi-lightning",
    },
    "stepfun": {
        "name": "阶跃星辰 (Step)",
        "type": "openai_compatible",
        "base_url": "https://api.stepfun.com/v1",
        "api_key": "",
        "model": "step-1-8k",
    },
    "custom": {
        "name": "自定义 OpenAI 兼容 API",
        "type": "openai_compatible",
        "base_url": "",
        "api_key": "",
        "model": "",
    },
}


# ---- 配置持久化 ----

def load_config() -> dict:
    """从磁盘加载服务商配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 合并：预设 + 用户保存的覆盖
            merged = {}
            for key, preset in PRESET_PROVIDERS.items():
                merged[key] = dict(preset)
                if key in saved:
                    merged[key].update(saved[key])
            # 添加用户自定义的额外服务商
            for key in saved:
                if key not in merged:
                    merged[key] = saved[key]
            return merged
        except Exception:
            pass
    return {k: dict(v) for k, v in PRESET_PROVIDERS.items()}


def save_config(config: dict):
    """将服务商配置保存到磁盘"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---- AI 提供者 ----

class AIProvider:
    """AI 提供者基类"""
    def __init__(self, name: str):
        self.name = name

    def chat(self, messages: list, stream: bool = False) -> str:
        raise NotImplementedError

    def fetch_models(self) -> List[str]:
        """获取可用模型列表"""
        return []


class OllamaProvider(AIProvider):
    """本地 Ollama 提供者"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        super().__init__("Ollama (本地)")
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _check_connection(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def chat(self, messages: list, stream: bool = False) -> str:
        # 先检测服务是否在线
        if not self._check_connection():
            return "[Ollama 未运行] 请先启动 Ollama 服务（ollama serve）"

        url = f"{self.base_url}/api/chat"

        # 转换消息格式为 Ollama 兼容格式
        ollama_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                # Ollama 不支持 system role，转为 user 消息并标记
                ollama_messages.append({"role": "system", "content": content})
            else:
                ollama_messages.append({"role": role, "content": content})

        payload = json.dumps({
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 2048,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("message", {}).get("content", "")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if e.code == 404:
                return f"[Ollama 错误] 模型 '{self.model}' 不存在，请先用 'ollama pull {self.model}' 安装"
            elif e.code == 400:
                return f"[Ollama 参数错误] {body[:200]}"
            else:
                return f"[Ollama HTTP {e.code}] {body[:200]}"
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", "")
            if isinstance(reason, Exception):
                reason = str(reason)
            return f"[Ollama 连接失败] 无法连接到 {self.base_url}，请确认 Ollama 正在运行: {reason}"
        except TimeoutError:
            return "[Ollama 超时] 响应超时（>180秒），请尝试使用更小的模型或简化问题"
        except json.JSONDecodeError as e:
            return f"[Ollama 解析错误] 返回数据格式异常: {e}"
        except Exception as e:
            err_type = type(e).__name__
            return f"[Ollama {err_type}] {e}"

    def fetch_models(self) -> List[str]:
        """从 Ollama 获取已安装的模型列表"""
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m["name"] for m in data.get("models", [])]
                return sorted(models)
        except Exception:
            return []


class OpenAICompatibleProvider(AIProvider):
    """OpenAI 兼容 API 提供者"""

    def __init__(self, api_key: str, base_url: str, model: str, name: str = "Cloud API"):
        super().__init__(name)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: list, stream: bool = False) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.7,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except urllib.error.URLError as e:
            return f"[API 连接失败] {e}"
        except KeyError:
            return "[API 响应格式错误]"
        except Exception as e:
            return f"[API 错误] {e}"

    def fetch_models(self) -> List[str]:
        """从 OpenAI 兼容 API 获取可用模型列表"""
        if not self.api_key:
            return []

        try:
            url = f"{self.base_url}/models"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

                models = []
                for item in data.get("data", []):
                    model_id = item.get("id", "")
                    if model_id:
                        models.append(model_id)

                return sorted(models)
        except Exception:
            return []


# ---- 模型获取工作线程 ----

class ModelFetchWorker(QThread):
    """异步获取模型列表的工作线程"""
    models_fetched = Signal(str, list)   # provider_key, [model_names]
    fetch_error = Signal(str, str)       # provider_key, error_message

    def __init__(self, provider_key: str, provider: AIProvider):
        super().__init__()
        self._key = provider_key
        self._provider = provider

    def run(self):
        try:
            models = self._provider.fetch_models()
            self.models_fetched.emit(self._key, models)
        except Exception as e:
            self.fetch_error.emit(self._key, str(e))


# ---- AI 引擎管理器 ----

class AIEngine:
    """AI 引擎管理器，统一调度不同 AI 提供者"""

    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}
        self._current_provider: Optional[str] = None
        self._config = load_config()

        # 根据配置初始化所有服务商
        self._init_providers_from_config()

    def _init_providers_from_config(self):
        """从配置文件初始化所有服务商"""
        for key, cfg in self._config.items():
            provider_type = cfg.get("type", "openai_compatible")
            if provider_type == "ollama":
                provider = OllamaProvider(
                    base_url=cfg.get("base_url", "http://localhost:11434"),
                    model=cfg.get("model", "qwen2.5:7b"),
                )
            else:
                provider = OpenAICompatibleProvider(
                    api_key=cfg.get("api_key", ""),
                    base_url=cfg.get("base_url", ""),
                    model=cfg.get("model", ""),
                    name=cfg.get("name", "Cloud API"),
                )
            self._providers[key] = provider

        # 默认选中第一个
        if self._current_provider is None and self._providers:
            self._current_provider = list(self._providers.keys())[0]

    def register_provider(self, key: str, provider: AIProvider):
        """注册 AI 提供者"""
        self._providers[key] = provider
        if self._current_provider is None:
            self._current_provider = key

    def remove_provider(self, key: str):
        """移除 AI 提供者"""
        if key in self._providers:
            del self._providers[key]
            if self._current_provider == key:
                self._current_provider = list(self._providers.keys())[0] if self._providers else None

    def set_current_provider(self, key: str):
        """切换当前 AI 提供者"""
        if key in self._providers:
            self._current_provider = key

    def get_current_provider(self) -> Optional[AIProvider]:
        """获取当前 AI 提供者"""
        if self._current_provider and self._current_provider in self._providers:
            return self._providers[self._current_provider]
        return None

    def get_current_provider_key(self) -> Optional[str]:
        return self._current_provider

    def get_provider(self, key: str) -> Optional[AIProvider]:
        return self._providers.get(key)

    def list_providers(self) -> dict:
        """列出所有已注册的提供者"""
        return {k: v.name for k, v in self._providers.items()}

    def get_config(self, key: str) -> Optional[dict]:
        """获取指定服务商的配置"""
        return self._config.get(key)

    def update_config(self, key: str, cfg: dict):
        """更新服务商配置并持久化"""
        self._config[key] = cfg
        save_config(self._config)

        # 同步更新 provider 实例
        provider_type = cfg.get("type", "openai_compatible")
        if provider_type == "ollama":
            provider = OllamaProvider(
                base_url=cfg.get("base_url", "http://localhost:11434"),
                model=cfg.get("model", "qwen2.5:7b"),
            )
        else:
            provider = OpenAICompatibleProvider(
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
                model=cfg.get("model", ""),
                name=cfg.get("name", "Cloud API"),
            )
        self._providers[key] = provider

    def save_all_config(self):
        """保存所有配置"""
        save_config(self._config)

    def fetch_models_async(self, key: str) -> Optional[ModelFetchWorker]:
        """异步获取指定服务商的模型列表"""
        provider = self._providers.get(key)
        if not provider:
            return None
        worker = ModelFetchWorker(key, provider)
        return worker

    def diagnose(self, context: str) -> str:
        """诊断网络/服务器问题"""
        provider = self.get_current_provider()
        if not provider:
            return "未配置 AI 提供者"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请分析以下终端输出/网络信息，诊断问题并给出建议：\n\n{context}"},
        ]
        return provider.chat(messages)

    def complete_command(self, context: str, current_input: str) -> str:
        """命令补全（用于 Ghost Text）"""
        provider = self.get_current_provider()
        if not provider:
            return ""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"根据以下终端上下文，补全用户正在输入的命令。\n"
                f"只返回补全部分，不要返回完整命令，不要解释。\n\n"
                f"上下文:\n{context}\n\n"
                f"用户当前输入: {current_input}"
            )},
        ]
        result = provider.chat(messages)
        result = result.strip().strip("`").strip()
        return result


# ---- 工作线程 ----

class AIChatWorker(QThread):
    """AI 对话工作线程"""
    response_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, engine: AIEngine, messages: list):
        super().__init__()
        self.engine = engine
        self.messages = messages

    def run(self):
        provider = self.engine.get_current_provider()
        if not provider:
            self.error_occurred.emit("未配置 AI 提供者")
            return
        try:
            result = provider.chat(self.messages)
            self.response_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))


class AICompletionWorker(QThread):
    """AI 补全工作线程（用于 Ghost Text）"""
    completion_ready = Signal(str)

    def __init__(self, engine: AIEngine, context: str, current_input: str):
        super().__init__()
        self.engine = engine
        self.context = context
        self.current_input = current_input

    def run(self):
        try:
            result = self.engine.complete_command(self.context, self.current_input)
            self.completion_ready.emit(result)
        except Exception:
            self.completion_ready.emit("")
