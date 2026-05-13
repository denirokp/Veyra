from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM — OpenAI-совместимый протокол (работает с Kimi/Moonshot, OpenAI, Avito proxy и др.)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.moonshot.ai/v1"
    LLM_MODEL: str = "kimi-k2.6"

    # Embeddings — локальная sentence-transformers модель (без интернета).
    # Первый запуск скачивает ~500МБ в ~/.cache/huggingface.
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

    # Storage
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/khronika.db"

    # Paths
    DOCS_DIR: str = "./data/docs"
    STYLE_ANCHORS_DIR: str = "./data/style_anchors"

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000


settings = Settings()
