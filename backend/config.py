import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    gemini_fallback_models: list[str] = _csv(
        os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-3.1-flash-lite")
    )
    gemini_thinking_level: str = os.getenv("GEMINI_THINKING_LEVEL", "low").strip()
    llm_max_concurrency: int = int(os.getenv("LLM_MAX_CONCURRENCY", "3"))
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "75"))

    data_dir: Path = BASE_DIR / "data"
    clone_dir: Path = BASE_DIR / "cloned_repos"
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"

    max_files: int = int(os.getenv("MAX_FILES", "1500"))
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", "200000"))
    clone_timeout_seconds: int = int(os.getenv("CLONE_TIMEOUT_SECONDS", "180"))

    cors_origins: list[str] = _csv(os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))

    @property
    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
