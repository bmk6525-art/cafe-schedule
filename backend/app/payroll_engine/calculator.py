"""
급여 계산 엔진 — 법률 기준은 설정값으로 분리

주휴수당 기준:
  - 1주 소정근로시간 15시간 이상 시 발생
  - 주휴수당 = (1주 근로시간 / 5) * 시급
  - 단, 5인 미만 사업장 등 실제 적용은 관리자 확인 필요
"""

from datetime import date
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.models import (
    Schedule, ActualWork, Employee, EmployeeType,
    MonthlyPayroll, WeeklyPayroll, Store,
)
from app.core.config import settings

_DOW_KO = ['월', '화', '수', '목', '금', '토', '일']


def _time_to_min(t: str) -> int:
    h, m = map(int, t.split(':'))
    return h * 60 + m


def _get_paid_minutes(start: str, end: str, break_min: int) -> int:
    return max(0, _time_to_min(end) - _time_to_min(start) - break_min)


def _month_range(year: int, month: int):
    start_date = date(year, month, 1)
    end_date = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    return start_date, end_date


def _calc_result_for_emp(emp: Employee, emp_schedules: list, actuals_map: dict, stores_map: dict) -> dict:
    """직원 1명의 급여 계산 (내부 헬퍼 — 이미 로드된 데이터 사용)"""
    threshold = settings.WEEKLY_HOLIDAY_PAY_THRESHOLD
    weekly_hours: dict[int, float] = defaultdict(float)
    total_minutes = 0
    daily_details = []

    for s in emp_schedules:
        actual = actuals_map.get(s.id)
        if actual and actual.is_absent:
            continue
        if actual and actual.actual_start and actual.actual_end:
            start = actual.actual_start
            end = actual.actual_end
            paid_min = _get_paid_minutes(start, end, actual.actual_break_minutes or 0)
        else:
            start = s.start_time
            end = s.end_time
            paid_min = _get_paid_minutes(start, end, s.break_minutes or 0)

        hours = round(paid_min / 60, 1)
        week_num = (s.work_date.day - 1) // 7 + 1
        weekly_hours[week_num] += hours
        total_minutes += paid_min

        store = stores_map.get(s.store_id) if s.store_id else None
        daily_details.append({
            'date': s.work_date.isoformat(),
            'day_of_week': _DOW_KO[s.work_date.weekday()],
            'start_time': start[:5],
            'end_time': end[:5],
            'hours': hours,
            'store_name': store.name if store else '',
            'is_actual': bool(actual and actual.actual_start),
        })

    total_holiday_pay = 0
    weekly_details = []
    for week_num in sorted(weekly_hours.keys()):
        wh = weekly_hours[week_num]
        eligible = wh >= threshold
        holiday_pay = round((wh / 5) * emp.hourly_wage) if eligible else 0
        total_holiday_pay += holiday_pay
        weekly_details.append({
            'week_num': week_num,
            'total_hours': round(wh, 2),
            'is_holiday_pay_eligible': eligible,
            'holiday_pay_amount': holiday_pay,
        })

    total_hours = round(total_minutes / 60, 2)
    base_pay = round(total_hours * emp.hourly_wage)
    total_pay = base_pay + total_holiday_pay

    return {
        'employee_id': emp.id,
        'employee_name': emp.name,
        'hourly_wage': emp.hourly_wage,
        'total_hours': total_hours,
        'base_pay': base_pay,
        'holiday_pay': total_holiday_pay,
        'total_pay': total_pay,
        'daily_details': daily_details,
        'weekly_details': weekly_details,
    }


def calculate_monthly_payroll(year: int, month: int, employee_id: int, db: Session) -> dict:
    """
    파트타이머 월별 급여 계산 (단일 직원)
    실제 근무시간이 있으면 실제 기준, 없으면 계획 기준으로 계산
    ActualWork·Store를 IN 쿼리로 배치 조회하여 N+1 방지
    """
    emp = db.query(Employee).filter_by(id=employee_id).first()
    if not emp:
        return {}

    start_date, end_date = _month_range(year, month)

    schedules = (
        db.query(Schedule)
        .filter(
            Schedule.employee_id == employee_id,
            Schedule.work_date >= start_date,
            Schedule.work_date < end_date,
            Schedule.is_cancelled == False,
        )
        .order_by(Schedule.work_date)
        .all()
    )

    # 배치 로드
    sch_ids = [s.id for s in schedules]
    actuals_map: dict[int, ActualWork] = {}
    if sch_ids:
        for a in db.query(ActualWork).filter(ActualWork.schedule_id.in_(sch_ids)).all():
            actuals_map[a.schedule_id] = a

    store_ids = list({s.store_id for s in schedules if s.store_id})
    stores_map: dict[int, Store] = {}
    if store_ids:
        for st in db.query(Store).filter(Store.id.in_(store_ids)).all():
            stores_map[st.id] = st

    result = _calc_result_for_emp(emp, schedules, actuals_map, stores_map)
    result['year'] = year
    result['month'] = month
    return result


def calculate_all_payroll(year: int, month: int, db: Session) -> list:
    """
    해당 월 전체 파트타이머 급여 계산 (배치 최적화)
    전체 스케줄·ActualWork·Store를 각각 1번 조회하여 N+1 완전 제거
    """
    start_date, end_date = _month_range(year, month)

    part_timers = db.query(Employee).filter_by(
        employee_type=EmployeeType.PART_TIMER, is_active=True
    ).all()
    if not part_timers:
        return []

    pt_ids = [pt.id for pt in part_timers]

    # 해당 월 전체 스케줄 한 번에 조회
    all_schedules = (
        db.query(Schedule)
        .filter(
            Schedule.employee_id.in_(pt_ids),
            Schedule.work_date >= start_date,
            Schedule.work_date < end_date,
            Schedule.is_cancelled == False,
        )
        .order_by(Schedule.work_date)
        .all()
    )

    # ActualWork 한 번에 조회
    sch_ids = [s.id for s in all_schedules]
    actuals_map: dict[int, ActualWork] = {}
    if sch_ids:
        for a in db.query(ActualWork).filter(ActualWork.schedule_id.in_(sch_ids)).all():
            actuals_map[a.schedule_id] = a

    # Store 한 번에 조회
    store_ids = list({s.store_id for s in all_schedules if s.store_id})
    stores_map: dict[int, Store] = {}
    if store_ids:
        for st in db.query(Store).filter(Store.id.in_(store_ids)).all():
            stores_map[st.id] = st

    # 직원별 스케줄 분배
    schedules_by_emp: dict[int, list] = defaultdict(list)
    for s in all_schedules:
        schedules_by_emp[s.employee_id].append(s)

    results = []
    for emp in part_timers:
        result = _calc_result_for_emp(emp, schedules_by_emp[emp.id], actuals_map, stores_map)
        result['year'] = year
        result['month'] = month
        result['is_finalized'] = False
        results.append(result)

    return results


# ── 급여 확정 관련 ──

def get_payroll_data(year: int, month: int, employee_id: int, db: Session) -> dict:
    """확정된 급여가 있으면 DB에서 반환, 없으면 실시간 계산"""
    payroll_rec = db.query(MonthlyPayroll).filter_by(
        employee_id=employee_id, year=year, month=month, is_finalized=True
    ).first()

    if payroll_rec:
        emp = db.query(Employee).filter_by(id=employee_id).first()
        weekly_recs = (
            db.query(WeeklyPayroll)
            .filter_by(monthly_payroll_id=payroll_rec.id)
            .order_by(WeeklyPayroll.week_number)
            .all()
        )
        weekly_details = [
            {
                'week_num': w.week_number,
                'total_hours': w.total_hours,
                'is_holiday_pay_eligible': w.is_holiday_pay_eligible,
                'holiday_pay_amount': w.holiday_pay_amount,
            }
            for w in weekly_recs
        ]
        # 일별 상세는 스케줄에서 재구성 (display용 — 확정 금액 자체는 DB 값 사용)
        live = calculate_monthly_payroll(year, month, employee_id, db)
        daily_details = live.get('daily_details', []) if live else []

        return {
            'employee_id': employee_id,
            'employee_name': emp.name if emp else '',
            'year': year,
            'month': month,
            'hourly_wage': payroll_rec.hourly_wage_snapshot,
            'total_hours': payroll_rec.total_work_hours,
            'base_pay': payroll_rec.base_pay,
            'holiday_pay': payroll_rec.holiday_pay,
            'total_pay': payroll_rec.total_pay,
            'is_finalized': True,
            'daily_details': daily_details,
            'weekly_details': weekly_details,
        }
    else:
        result = calculate_monthly_payroll(year, month, employee_id, db)
        if result:
            result['is_finalized'] = False
        return result


def finalize_employee_payroll(year: int, month: int, employee_id: int, db: Session):
    """직원 급여 확정 — 계산 결과를 MonthlyPayroll·WeeklyPayroll에 저장"""
    result = calculate_monthly_payroll(year, month, employee_id, db)
    if not result:
        return None

    emp = db.query(Employee).filter_by(id=employee_id).first()
    if not emp:
        return None

    payroll_rec = db.query(MonthlyPayroll).filter_by(
        employee_id=employee_id, year=year, month=month
    ).first()
    if not payroll_rec:
        payroll_rec = MonthlyPayroll(employee_id=employee_id, year=year, month=month)
        db.add(payroll_rec)

    payroll_rec.hourly_wage_snapshot = emp.hourly_wage
    payroll_rec.total_work_hours = result['total_hours']
    payroll_rec.base_pay = result['base_pay']
    payroll_rec.holiday_pay = result['holiday_pay']
    payroll_rec.total_pay = result['total_pay']
    payroll_rec.is_finalized = True

    db.flush()

    # 주차별 데이터 저장 (기존 레코드 교체)
    db.query(WeeklyPayroll).filter_by(
        employee_id=employee_id, year=year, month=month
    ).delete()

    for wd in result['weekly_details']:
        db.add(WeeklyPayroll(
            monthly_payroll_id=payroll_rec.id,
            employee_id=employee_id,
            year=year, month=month,
            week_number=wd['week_num'],
            total_hours=wd['total_hours'],
            is_holiday_pay_eligible=wd['is_holiday_pay_eligible'],
            holiday_pay_amount=wd['holiday_pay_amount'],
        ))

    return payroll_rec


def finalize_all_payroll(year: int, month: int, db: Session) -> dict:
    """해당 월 전체 활성 파트타이머 급여 확정"""
    part_timers = db.query(Employee).filter_by(
        employee_type=EmployeeType.PART_TIMER, is_active=True
    ).all()
    count = 0
    for pt in part_timers:
        if finalize_employee_payroll(year, month, pt.id, db):
            count += 1
    db.commit()
    return {'finalized_count': count}
