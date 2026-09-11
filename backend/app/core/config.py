from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "카페 근무 스케줄 관리"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./cafe_schedule.db"

    FRONTEND_URL: str = "http://localhost:5173"

    ANTHROPIC_API_KEY: Optional[str] = None

    SECRET_KEY: str = "change-this-to-a-random-secret-key"

    # 정규직 기본 근무 설정 (향후 변경 가능하도록 설정값으로 관리)
    REGULAR_WORK_DAYS_PER_WEEK: int = 5
    REGULAR_WORK_HOURS_PER_WEEK: int = 40
    REGULAR_DAILY_STAY_HOURS: int = 9   # 매장 체류 시간
    REGULAR_BREAK_HOURS: float = 1.0    # 휴게시간
    REGULAR_PAID_HOURS: float = 8.0     # 유급 근무시간

    # 주휴수당 기준 주간 근무시간 (법령 기준 15시간)
    WEEKLY_HOLIDAY_PAY_THRESHOLD: float = 15.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
