from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM — OpenAI-совместимый протокол (работает с Kimi/Moonshot, OpenAI, Avito proxy и др.)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.moonshot.ai/v1"
    LLM_MODEL: str = "moonshot-v1-128k"
    # Модель для механических skills (извлечение сущностей и обещаний при
    # индексации). Извлечение не требует глубокого рассуждения — сюда можно
    # поставить дешёвую/быструю модель. Пусто → используется LLM_MODEL.
    LLM_MODEL_FAST: str = ""

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

    # CORS — список origin'ов через запятую. По умолчанию только локальный фронт.
    CORS_ORIGINS: str = "http://localhost:5173"

    # Web search — опционально, для "внешнего опыта" в full-mode ответах.
    # Активируется только если задан один из ключей. Tavily приоритетнее
    # (лучше для research-задач). Brave дешевле/бесплатнее на низких объёмах.
    TAVILY_API_KEY: str = ""
    BRAVE_API_KEY: str = ""

    # При bulk-индексации больших корпусов можно отключить дорогие LLM-skills
    # (logic signals — pairwise сравнение пар документов).
    DISABLE_LOGIC_SIGNALS: bool = False

    # Числовой детектор расхождений (extract_entities → find_contradictions
    # и numeric-часть find_intra_contradictions). Отключён по умолчанию:
    # на валидации (scripts/eval_detectors.py) дал precision 11% — фабрикует
    # несуществующие значения, не нормализует единицы/округление, путает
    # «план vs факт». Числовые расхождения ищет Claude на запросе (целевая
    # архитектура; гейт Фазы 1 это подтвердил). Логический и promise-детекторы
    # валидацию прошли (83% / 94%) и работают штатно.
    ENABLE_NUMERIC_CONTRADICTIONS: bool = False

    # При индексации запускать background-skills (extract_entities →
    # числовые расхождения, track_promises, find_logic_signals) и генерацию
    # document brief. Это и есть "бульон" — без них система работает как
    # обычный RAG-поиск без проактивных находок. Включено по умолчанию;
    # выключать имеет смысл только при bulk-индексации огромных корпусов
    # (ENABLE_BACKGROUND_SIGNALS=0), чтобы не тратить ~6 LLM-вызовов на документ.
    ENABLE_BACKGROUND_SIGNALS: bool = True

    # Опциональная авторизация по статичному bearer-токену. Если задан —
    # все API endpoints кроме /health требуют заголовок
    #   Authorization: Bearer <API_AUTH_TOKEN>
    # Если пуст (по умолчанию) — API открыт (local dev / без auth).
    # Минимум 16 символов рекомендуется для прода.
    API_AUTH_TOKEN: str = ""

    # Максимальный размер JSON body для chat/initiative — защита от
    # случайного 50MB body, который положит LLM-контекст и/или память.
    MAX_REQUEST_BODY_MB: int = 5

    # Серверный «мозг» POST /api/chat (orchestrator + docs-agent, LLM на
    # живом пути) — LEGACY. Продуктовый живой путь — Claude через
    # veyra-mcp; серверный /api/chat нужен только React-админ-панели.
    # В production-деплое без панели можно выключить
    # (ENABLE_LEGACY_CHAT=0) — останется чистый слой данных (/api/retrieve
    # и data-эндпоинты), который и потребляет veyra-mcp.
    ENABLE_LEGACY_CHAT: bool = True


settings = Settings()
