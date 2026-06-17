"""
大模型模块 - 对接 DeepSeek / OpenAI 兼容接口
"""
import logging

logger = logging.getLogger(__name__)


class LLMEngine:
    """大模型对话引擎"""

    def __init__(self, config: dict):
        self.config = config.get("llm", {})
        self.client = None
        self._init_client()

    def _init_client(self):
        from openai import OpenAI

        provider = self.config.get("provider", "openai")
        api_key = self.config.get("api_key", "")
        base_url = self.config.get("base_url", "")

        if not api_key:
            raise ValueError("请配置 LLM API Key")

        logger.info(f"初始化 LLM 客户端: provider={provider}, base_url={base_url}")

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url if base_url else None,
        )

    def chat(self, text: str, history: list[dict] = None) -> str:
        """对话

        Args:
            text: 用户输入的文本
            history: 历史对话 (可选)

        Returns:
            AI 回复文本
        """
        model = self.config.get("model", "deepseek-v4-flash")
        system_prompt = self.config.get(
            "system_prompt",
            "你是一个智能语音助手，请用中文简洁回答，控制在50字以内，适合语音播报。",
        )

        messages = [{"role": "system", "content": system_prompt}]

        # 添加历史对话（保留最近3轮）
        if history:
            for h in history[-3:]:
                messages.append(h)

        messages.append({"role": "user", "content": text})

        logger.info(f"LLM 请求: model={model}, 输入='{text}'")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=200,
                temperature=0.7,
            )

            reply = response.choices[0].message.content.strip()
            logger.info(f"LLM 回复: '{reply}'")
            return reply

        except Exception as e:
            logger.error(f"LLM 请求失败: {e}")
            return f"抱歉，我遇到了一点问题：{str(e)}"

    def stream_chat(self, text: str, history: list[dict] = None):
        """流式对话（用于 Web 界面实时显示）"""
        model = self.config.get("model", "deepseek-v4-flash")
        system_prompt = self.config.get(
            "system_prompt",
            "你是一个智能语音助手，请用中文简洁回答。",
        )

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history[-3:]:
                messages.append(h)
        messages.append({"role": "user", "content": text})

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=200,
            temperature=0.7,
            stream=True,
        )

        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content