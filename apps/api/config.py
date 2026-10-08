from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./data/app.db"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Upload
    max_upload_size_mb: int = 50
    upload_dir: str = "uploads"
    audio_dir: str = "data/audio"

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # Generation defaults
    default_difficulty: str = "medium"
    default_style: str = "teacher"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
