"""
AttitudeEngine 配置
自身 .env 独立于 MindSpider，不与 BettaFish 共享
"""

from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    # --- 数据库 ---
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5444
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_NAME: str = "mindspider"

    # --- LLM API ---
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    # --- Spark Lite（主力标注） ---
    SPARK_API_KEY: str = ""
    SPARK_BASE_URL: str = "https://spark-api-open.xf-yun.com/v1"
    SPARK_MODEL: str = "lite"

    # --- 标注 ---
    BATCH_SIZE: int = 20

    # --- 输出 ---
    OUTPUT_DIR: str = "outputs"

    class Config:
        env_file = str(Path(__file__).parent / ".env")
        env_prefix = ""
        case_sensitive = False


settings = Settings()

# 自动创建输出目录
Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
