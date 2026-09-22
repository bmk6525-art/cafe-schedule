"""
카페 근무 스케줄 관리 - FastAPI 메인 애플리케이션
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from app.database.database import get_db

from app.core.config import settings
from app.database.database import init_db
from app.api.v1 import employees, stores, work_patterns, availability, staff_requirements, schedules, payroll, monthly, history, dashboard


def _run_migrations():
    """기존 DB에 누락된 컬럼·인덱스 추가"""
    from sqlalchemy import text, inspect as sa_inspect
    from app.database.database import engine as _engine
    insp = sa_inspect(_engine)

    with _engine.connect() as conn:
        # is_available_override 컬럼 추가 (이전 마이그레이션)
        if 'availability_exceptions' in insp.get_table_names():
            cols = {c['name'] for c in insp.get_columns('availability_exceptions')}
            if 'is_available_override' not in cols:
                conn.execute(text(
                    "ALTER TABLE availability_exceptions "
                    "ADD COLUMN is_available_override BOOLEAN NOT NULL DEFAULT false"
                ))

        # schedules 성능 인덱스 추가 — 풀스캔 방지
        if 'schedules' in insp.get_table_names():
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_schedules_date_status "
                "ON schedules (work_date, is_cancelled, status)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_schedules_emp_date "
                "ON schedules (employee_id, work_date)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_schedules_store_date "
                "ON schedules (store_id, work_date)"
            ))

        # monthly_availability 가능시간 컬럼 추가 (3차 개선)
        if 'monthly_availability' in insp.get_table_names():
            ma_cols = {c['name'] for c in insp.get_columns('monthly_availability')}
            if 'entry_type' not in ma_cols:
                conn.execute(text(
                    "ALTER TABLE monthly_availability "
                    "ADD COLUMN entry_type VARCHAR(20) NOT NULL DEFAULT 'UNAVAILABLE'"
                ))
            if 'is_working_day' not in ma_cols:
                conn.execute(text(
                    "ALTER TABLE monthly_availability "
                    "ADD COLUMN is_working_day BOOLEAN NOT NULL DEFAULT 0"
                ))
            if 'available_start' not in ma_cols:
                conn.execute(text(
                    "ALTER TABLE monthly_availability "
                    "ADD COLUMN available_start VARCHAR(5)"
                ))
            if 'available_end' not in ma_cols:
                conn.execute(text(
                    "ALTER TABLE monthly_availability "
                    "ADD COLUMN available_end VARCHAR(5)"
                ))

        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB 초기화 및 마이그레이션"""
    init_db()
    _run_migrations()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="카페 직원 및 파트타이머 근무 스케줄 통합 관리 시스템",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 설정 - nginx 프록시 사용 시 같은 origin이므로 모두 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(employees.router, prefix="/api/v1")
app.include_router(stores.router, prefix="/api/v1")
app.include_router(work_patterns.router, prefix="/api/v1")
app.include_router(availability.router, prefix="/api/v1")
app.include_router(staff_requirements.router, prefix="/api/v1")
app.include_router(schedules.router, prefix="/api/v1")
app.include_router(payroll.router, prefix="/api/v1")
app.include_router(monthly.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "message": f"{settings.APP_NAME} API",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/v1/seed")
def run_seed(db: Session = Depends(get_db)):
    """개발용 초기 데이터 생성 (한 번만 실행)"""
    from app.database.seed import run_seed as _run_seed
    _run_seed(db)
    return {"message": "Seed 데이터가 성공적으로 생성되었습니다.", "success": True}
