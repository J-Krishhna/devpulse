from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    groq_api_key: str
    gemini_api_key: str
    github_webhook_secret: str

        # ✅ Add these
    hf_token: str | None = None
    huggingfacehub_api_token: str | None = None

    class Config:
        env_file = ".env"

settings = Settings()