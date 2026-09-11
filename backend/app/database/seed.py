"""
개발용 초기 데이터 (Seed Data)
실제 개인정보를 사용하지 않는 테스트 데이터
"""

from datetime import date
from sqlalchemy.orm import Session
from app.models.models import Store, Employee, EmployeeType, DayOfWeek, EmployeeWorkPattern


def seed_stores(db: Session) -> list[Store]:
    """기본 매장 3개 생성"""
    stores_data = [
        {"name": "1호점", "open_time": "10:00", "close_time": "23:00"},
        {"name": "2호점", "open_time": "08:30", "close_time": "23:00"},
        {"name": "3호점", "open_time": "09:00", "close_time": "23:00"},
    ]
    stores = []
    for data in stores_data:
        existing = db.query(Store).filter(Store.name == data["name"]).first()
        if not existing:
            store = Store(**data)
            db.add(store)
            stores.append(store)
        else:
            stores.append(existing)
    db.commit()
    for s in stores:
        if s.id is None:
            db.refresh(s)
    return stores


def seed_employees(db: Session, stores: list[Store]) -> list[Employee]:
    """테스트 직원 데이터 생성"""
    employees_data = [
        # 정규직 3명
        {
            "name": "직원A",
            "employee_type": EmployeeType.REGULAR,
            "hourly_wage": 10030,   # 2024 최저임금 기준
            "hire_date": date(2022, 3, 1),
            "preferred_store_id": stores[0].id,
            "memo": "테스트 정규직 직원",
        },
        {
            "name": "직원B",
            "employee_type": EmployeeType.REGULAR,
            "hourly_wage": 10030,
            "hire_date": date(2022, 6, 1),
            "preferred_store_id": stores[1].id,
            "memo": "테스트 정규직 직원",
        },
        {
            "name": "직원C",
            "employee_type": EmployeeType.REGULAR,
            "hourly_wage": 10030,
            "hire_date": date(2023, 1, 1),
            "preferred_store_id": stores[2].id,
            "memo": "테스트 정규직 직원",
        },
        # 파트타이머 5명
        {
            "name": "파트A",
            "employee_type": EmployeeType.PART_TIMER,
            "hourly_wage": 10030,
            "hire_date": date(2024, 1, 1),
            "preferred_store_id": stores[0].id,
            "monthly_target_hours": 60,
            "monthly_min_hours": 40,
            "monthly_max_hours": 80,
            "memo": "테스트 파트타이머",
        },
        {
            "name": "파트B",
            "employee_type": EmployeeType.PART_TIMER,
            "hourly_wage": 10030,
            "hire_date": date(2024, 3, 1),
            "preferred_store_id": stores[1].id,
            "monthly_target_hours": 50,
            "monthly_min_hours": 30,
            "monthly_max_hours": 70,
            "memo": "테스트 파트타이머",
        },
        {
            "name": "파트C",
            "employee_type": EmployeeType.PART_TIMER,
            "hourly_wage": 10030,
            "hire_date": date(2024, 5, 1),
            "preferred_store_id": stores[2].id,
            "monthly_target_hours": 40,
            "monthly_min_hours": 20,
            "monthly_max_hours": 60,
            "memo": "테스트 파트타이머",
        },
        {
            "name": "파트D",
            "employee_type": EmployeeType.PART_TIMER,
            "hourly_wage": 10030,
            "hire_date": date(2024, 7, 1),
            "preferred_store_id": stores[0].id,
            "monthly_target_hours": 60,
            "monthly_min_hours": 40,
            "monthly_max_hours": 80,
            "memo": "테스트 파트타이머",
        },
        {
            "name": "파트E",
            "employee_type": EmployeeType.PART_TIMER,
            "hourly_wage": 10030,
            "hire_date": date(2024, 9, 1),
            "preferred_store_id": stores[1].id,
            "monthly_target_hours": 50,
            "monthly_min_hours": 30,
            "monthly_max_hours": 70,
            "memo": "테스트 파트타이머",
        },
    ]

    employees = []
    for data in employees_data:
        existing = db.query(Employee).filter(Employee.name == data["name"]).first()
        if not existing:
            employee = Employee(**data)
            db.add(employee)
            employees.append(employee)
        else:
            employees.append(existing)
    db.commit()
    for e in employees:
        if e.id is None:
            db.refresh(e)
    return employees


def seed_work_patterns(db: Session, employees: list[Employee], stores: list[Store]):
    """정규직 기본 근무패턴 생성 (월~금 09:00~18:00, 토일 휴무)"""
    regular_employees = [e for e in employees if e.employee_type == EmployeeType.REGULAR]

    work_days = [DayOfWeek.MON, DayOfWeek.TUE, DayOfWeek.WED, DayOfWeek.THU, DayOfWeek.FRI]
    off_days = [DayOfWeek.SAT, DayOfWeek.SUN]

    for i, emp in enumerate(regular_employees):
        existing = db.query(EmployeeWorkPattern).filter(
            EmployeeWorkPattern.employee_id == emp.id
        ).first()
        if existing:
            continue

        store = stores[i % len(stores)]
        for day in work_days:
            pattern = EmployeeWorkPattern(
                employee_id=emp.id,
                day_of_week=day,
                is_day_off=False,
                start_time="09:00",
                end_time="18:00",
                store_id=store.id,
            )
            db.add(pattern)
        for day in off_days:
            pattern = EmployeeWorkPattern(
                employee_id=emp.id,
                day_of_week=day,
                is_day_off=True,
                start_time=None,
                end_time=None,
                store_id=None,
            )
            db.add(pattern)
    db.commit()


def run_seed(db: Session):
    """전체 Seed 실행"""
    print("Seed 데이터 생성 시작...")
    stores = seed_stores(db)
    print(f"  매장 {len(stores)}개 생성/확인 완료")

    employees = seed_employees(db, stores)
    print(f"  직원 {len(employees)}명 생성/확인 완료")

    seed_work_patterns(db, employees, stores)
    print("  근무패턴 생성/확인 완료")

    print("Seed 데이터 생성 완료!")
