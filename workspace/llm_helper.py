"""Gọi LLM online để hỗ trợ luyện tập - đổi provider qua .env, không sửa code này.

Dùng:
    from llm_helper import ask
    print(ask("Giải thích XGBoost hoạt động thế nào?"))
"""
import os

from openai import OpenAI

_client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
)
_MODEL = os.environ.get("LLM_MODEL", "deepseek/deepseek-r1-distill-qwen-32b")


def ask(prompt: str, system: str | None = None, **kwargs) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = _client.chat.completions.create(model=_MODEL, messages=messages, **kwargs)
    return resp.choices[0].message.content
