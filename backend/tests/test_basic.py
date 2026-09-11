"""
PHASE 1~3 기본 테스트
- DB 연결, 테이블 생성, 기본 CRUD 확인
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database.database import Base, get_db
from app.models.models import Store, Employee, EmployeeType


# 테스트용 인메모리 SQLite DB
TEST_DATABASE_URL = "sqlite:///./test_cafe_schedule.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def client():
    """테스트 클라이언트 설정"""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def db():
    """테스트 DB 세션"""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ───────────────────────────────────────────────
# Health Check 테스트
# ───────────────────────────────────────────────

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ───────────────────────────────────────────────
# 매장(Store) CRUD 테스트
# ───────────────────────────────────────────────

def test_create_store(client):
    """매장 추가 테스트"""
    response = client.post("/api/v1/stores", json={
        "name": "테스트 1호점",
        "open_time": "10:00",
        "close_time": "23:00",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "테스트 1호점"
    assert data["open_time"] == "10:00"
    assert data["close_time"] == "23:00"
    assert data["is_active"] == True


def test_create_store_duplicate_name(client):
    """중복 매장 이름 방지 테스트"""
    client.post("/api/v1/stores", json={"name": "중복 매장", "open_time": "10:00", "close_time": "23:00"})
    response = client.post("/api/v1/stores", json={"name": "중복 매장", "open_time": "09:00", "close_time": "22:00"})
    assert response.status_code == 400


def test_get_stores(client):
    """매장 목록 조회 테스트"""
    client.post("/api/v1/stores", json={"name": "A호점", "open_time": "10:00", "close_time": "23:00"})
    client.post("/api/v1/stores", json={"name": "B호점", "open_time": "09:00", "close_time": "22:00"})
    response = client.get("/api/v1/stores")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_update_store(client):
    """매장 정보 수정 테스트"""
    create_response = client.post("/api/v1/stores", json={
        "name": "수정 테스트 매장",
        "open_time": "10:00",
        "close_time": "23:00",
    })
    store_id = create_response.json()["id"]
    response = client.put(f"/api/v1/stores/{store_id}", json={"open_time": "09:00"})
    assert response.status_code == 200
    assert response.json()["open_time"] == "09:00"


def test_deactivate_store(client):
    """매장 비활성화(soft delete) 테스트"""
    create_response = client.post("/api/v1/stores", json={
        "name": "비활성화 매장",
        "open_time": "10:00",
        "close_time": "23:00",
    })
    store_id = create_response.json()["id"]
    delete_response = client.delete(f"/api/v1/stores/{store_id}")
    assert delete_response.status_code == 200

    # 기본 조회에서는 보이지 않아야 함
    stores = client.get("/api/v1/stores").json()
    assert all(s["id"] != store_id for s in stores)

    # include_inactive=true 에서는 보여야 함
    stores_all = client.get("/api/v1/stores?include_inactive=true").json()
    assert any(s["id"] == store_id for s in stores_all)


# ───────────────────────────────────────────────
# 직원(Employee) CRUD 테스트
# ───────────────────────────────────────────────

def test_create_employee(client):
    """직원 추가 테스트"""
    response = client.post("/api/v1/employees", json={
        "name": "홍길동",
        "employee_type": "PART_TIMER",
        "hourly_wage": 10030,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "홍길동"
    assert data["employee_type"] == "PART_TIMER"
    assert data["is_active"] == True


def test_create_regular_employee(client):
    """정규직 추가 테스트"""
    response = client.post("/api/v1/employees", json={
        "name": "김철수",
        "employee_type": "REGULAR",
        "hourly_wage": 10030,
        "hire_date": "2022-01-01",
    })
    assert response.status_code == 201
    assert response.json()["employee_type"] == "REGULAR"


def test_get_employees_by_type(client):
    """직원 타입 필터 조회 테스트"""
    client.post("/api/v1/employees", json={"name": "정규직1", "employee_type": "REGULAR", "hourly_wage": 10030})
    client.post("/api/v1/employees", json={"name": "파트타이머1", "employee_type": "PART_TIMER", "hourly_wage": 10030})
    client.post("/api/v1/employees", json={"name": "파트타이머2", "employee_type": "PART_TIMER", "hourly_wage": 10030})

    regulars = client.get("/api/v1/employees?employee_type=REGULAR").json()
    assert len(regulars) == 1

    parts = client.get("/api/v1/employees?employee_type=PART_TIMER").json()
    assert len(parts) == 2


def test_update_employee(client):
    """직원 정보 수정 테스트"""
    create_response = client.post("/api/v1/employees", json={
        "name": "수정 테스트",
        "employee_type": "PART_TIMER",
        "hourly_wage": 10030,
    })
    emp_id = create_response.json()["id"]
    response = client.put(f"/api/v1/employees/{emp_id}", json={"hourly_wage": 11000})
    assert response.status_code == 200
    assert response.json()["hourly_wage"] == 11000


def test_deactivate_employee(client):
    """직원 비활성화(soft delete) 테스트"""
    create_response = client.post("/api/v1/employees", json={
        "name": "비활성화 직원",
        "employee_type": "PART_TIMER",
        "hourly_wage": 10030,
    })
    emp_id = create_response.json()["id"]
    client.delete(f"/api/v1/employees/{emp_id}")

    employees = client.get("/api/v1/employees").json()
    assert all(e["id"] != emp_id for e in employees)

    employees_all = client.get("/api/v1/employees?include_inactive=true").json()
    assert any(e["id"] == emp_id for e in employees_all)


# ───────────────────────────────────────────────
# Seed 데이터 테스트
# ───────────────────────────────────────────────

def test_seed_data(client):
    """Seed 데이터 생성 테스트"""
    response = client.post("/api/v1/seed")
    assert response.status_code == 200
    assert response.json()["success"] == True

    stores = client.get("/api/v1/stores").json()
    assert len(stores) == 3
    assert stores[0]["name"] == "1호점"

    employees = client.get("/api/v1/employees").json()
    assert len(employees) == 8  # 정규직 3 + 파트타이머 5


# ───────────────────────────────────────────────
# 근무패턴(WorkPattern) 테스트
# ───────────────────────────────────────────────

def test_work_pattern_regular(client):
    """정규직 근무패턴 저장/조회 테스트"""
    # 매장 생성
    store_res = client.post("/api/v1/stores", json={"name": "패턴 테스트 매장", "open_time": "09:00", "close_time": "23:00"})
    store_id = store_res.json()["id"]

    # 정규직 직원 생성
    emp_res = client.post("/api/v1/employees", json={"name": "근무패턴 직원", "employee_type": "REGULAR", "hourly_wage": 10030})
    emp_id = emp_res.json()["id"]

    # 7일 근무패턴 저장
    patterns = [
        {"day_of_week": day, "is_day_off": day in ["SAT", "SUN"],
         "start_time": None if day in ["SAT", "SUN"] else "09:00",
         "end_time": None if day in ["SAT", "SUN"] else "18:00",
         "store_id": None if day in ["SAT", "SUN"] else store_id}
        for day in ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    ]
    res = client.put(f"/api/v1/employees/{emp_id}/work-patterns", json={"patterns": patterns})
    assert res.status_code == 200
    assert len(res.json()) == 7

    # 조회
    get_res = client.get(f"/api/v1/employees/{emp_id}/work-patterns")
    assert get_res.status_code == 200
    data = get_res.json()
    mon = next(d for d in data if d["day_of_week"] == "MON")
    assert mon["is_day_off"] == False
    assert mon["start_time"] == "09:00"
    sat = next(d for d in data if d["day_of_week"] == "SAT")
    assert sat["is_day_off"] == True


def test_work_pattern_part_timer_rejected(client):
    """파트타이머에게 근무패턴 설정 시 오류 확인"""
    emp_res = client.post("/api/v1/employees", json={"name": "파트타이머X", "employee_type": "PART_TIMER", "hourly_wage": 10030})
    emp_id = emp_res.json()["id"]
    res = client.get(f"/api/v1/employees/{emp_id}/work-patterns")
    assert res.status_code == 400


# ───────────────────────────────────────────────
# PHASE 3 — 매장(Store) 추가 테스트
# ───────────────────────────────────────────────

def test_store_operating_hours_validation(client):
    """운영시간 형식 검증"""
    # 정상
    res = client.post("/api/v1/stores", json={"name": "정상 매장", "open_time": "10:00", "close_time": "23:00"})
    assert res.status_code == 201

    # 잘못된 시간 형식
    res = client.post("/api/v1/stores", json={"name": "오류 매장", "open_time": "10시", "close_time": "23:00"})
    assert res.status_code == 422


def test_store_reactivation(client):
    """비활성화된 매장을 수정으로 다시 활성화"""
    res = client.post("/api/v1/stores", json={"name": "재활성 매장", "open_time": "10:00", "close_time": "23:00"})
    store_id = res.json()["id"]

    client.delete(f"/api/v1/stores/{store_id}")

    # 비활성 상태 확인
    stores = client.get("/api/v1/stores").json()
    assert all(s["id"] != store_id for s in stores)

    # PUT으로 is_active=True 복구
    client.put(f"/api/v1/stores/{store_id}", json={"is_active": True})
    stores = client.get("/api/v1/stores").json()
    assert any(s["id"] == store_id for s in stores)
