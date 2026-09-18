from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-5.6-luna"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "medium"
    firebase_project_id: str | None = None
    firestore_cohorts_collection: str = "cohorts"
    firestore_resumes_collection: str = "resumes"
    firestore_ai_reviews_collection: str = "aiReviews"
    # 공고별 요건 정리 결과. job_id + 공고 hash + 요건 지시문 버전으로 문서를 나눈다.
    firestore_job_requirements_collection: str = "jobRequirementProfiles"
    matching_job_store_path: Path = BASE_DIR.parent / "job_matching_bot" / "artifacts" / "job_store.sqlite"


@lru_cache
def get_settings() -> Settings:
    return Settings()
