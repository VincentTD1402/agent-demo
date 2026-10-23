"""Factory tạo chat model và embedding trỏ tới server AI tự host."""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.settings.api import ApiSettings


def build_chat_model(s: ApiSettings) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        model=s.llm_model,
        temperature=s.llm_temperature,
        timeout=s.llm_timeout_s,
        max_retries=2,
    )


def build_embeddings(s: ApiSettings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        base_url=s.embedding_base_url or s.llm_base_url,
        api_key=s.embedding_api_key or s.llm_api_key,
        model=s.embedding_model,
        # Server không phải OpenAI: gửi chuỗi thô, không tokenize bằng tiktoken
        check_embedding_ctx_length=False,
    )
