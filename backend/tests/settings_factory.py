"""Settings dựng tay cho test, không đọc .env/môi trường thật."""

from app.settings import Settings


def make_settings(**overrides) -> Settings:
    values = dict(
        postgres_db="x", postgres_user="x", postgres_password="x",
        embedding_api_url="http://embed.invalid/v1", embedding_model_name="m",
        llm_api_url="http://llm.invalid/v1", llm_model_name="m",
        reranker_api_url="http://rerank.invalid/v1", reranker_model_name="m",
        api_key="",  # không để API_KEY trong .env/môi trường thật lọt vào test
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)
