from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = ""
    LLM_MODEL: str = "claude-sonnet-4-20250514"

    # Embeddings
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-large"

    # Storage
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/khronika.db"

    # Paths
    CORPUS_DIR: str = "./data/corpus"
    STYLE_ANCHORS_DIR: str = "./data/style_anchors"

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]


settings = Settings()
