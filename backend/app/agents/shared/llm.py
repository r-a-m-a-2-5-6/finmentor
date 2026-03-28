"""
finmentor — Shared LLM Factory
================================
Central place to swap model providers.
"""

# from langchain.chat_models import ChatOpenAI
# from app.config import settings

# def get_llm(temperature: float = 0.2) -> ChatOpenAI:
#     """Return a configured LLM instance."""
#     return ChatOpenAI(
#         model_name="gpt-4o-mini",
#         temperature=temperature,
#         openai_api_key=settings.OPENAI_API_KEY
#     )

from langchain_openai import ChatOpenAI
from app.config import settings

def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini",   # ✅ use 'model' not 'model_name'
        temperature=temperature,
        api_key=settings.OPENAI_API_KEY
    )
