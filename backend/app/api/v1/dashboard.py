from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from collections import defaultdict

from app.database.database import get_db
from app.models.models import (
    Schedule, Employee, Store, StaffRequirement,
    ActualWork, EmployeeType, ScheduleStatus
)
from app.core.config import settings

router = APIRouter(tags=["대시보드"])


def _t(s: str) -> int:
    h, m = map(int, s.split(':'))
    return h * 60 + m


@router.get("/dashboard/stats")
def get_dashboard_stats(year: int, month: int, db: Session = Depends(get_db)):
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    schedules = db.query(Schedule).filter(
        Schedule.work_date >= start,
        Schedule.work_date < end,
        Schedule.is_cancelled == False,
    ).all()

    # 총 스케줄 수
    total_schedules = len(schedules)

    # 파트타이머 총 근무시간 & 예상 인건비
    total_minutes = 0
    total_labor_cost = 0.0
    weekly_hours_by_pt: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for s in schedules:
        emp = db.query(Employee).filter_by(id=s.employee_id).first()
        if not emp:
            continue
        actual = db.query(ActualWork).filter_by(schedule_id=s.id).first()
        if actual and actual.is_absent:
            continue
        if actual and actual.actual_start and actual.actual_end:
            mins = max(0, _t(actual.actual_end) - _t(actual.actual_start) - actual.actual_break_minutes)
        else:
            mins = max(0, _t(s.end_time) - _t(s.start_time) - s.break_minutes)

        if emp.employee_type == EmployeeType.PART_TIMER:
            total_minutes += mins
            total_labor_cost += (mins / 60) * emp.hourly_wage
            week_num = (s.work_date.day - 1) // 7 + 1
            weekly_hours_by_pt[emp.id][week_num] += mins / 60

    # 주휴수당 위험 인원 (이번 달 기준 한 주라도 15h 초과)
    threshold = settings.WEEKLY_HOLIDAY_PAY_THRESHOLD
    holiday_risk_count = 0
    for pt_id, weeks in weekly_hours_by_pt.items():
        if any(h >= threshold for h in weeks.values()):
            holiday_risk_count += 1

    # 인원 부족 슬롯 수: 요구 인원 대비 실제 배치 부족 카운트
    requirements = db.query(StaffRequirement).filter_by(year=year, month=month).all()
    understaffed_count = 0
    for req in requirements:
        # 해당 요일의 해당 시간대 배치 인원 계산
        slot_count = 0
        for s in schedules:
            if s.store_id != req.store_id:
                continue
            dow_val = s.work_date.strftime('%A').upper()[:3]
            dow_map = {'MON':'MONDAY','TUE':'TUESDAY','WED':'WEDNESDAY',
                       'THU':'THURSDAY','FRI':'FRIDAY','SAT':'SATURDAY','SUN':'SUNDAY'}
            full_dow = dow_map.get(dow_val, '')
            if req.day_of_week.value != full_dow:
                continue
            if _t(s.start_time) <= _t(req.start_time) and _t(s.end_time) >= _t(req.end_time):
                slot_count += 1
        if slot_count < req.required_count:
            understaffed_count += 1

    total_hours = round(total_minutes / 60, 1)

    # 주휴수당 포함 예상 추가 비용
    for pt_id, weeks in weekly_hours_by_pt.items():
        emp = db.query(Employee).filter_by(id=pt_id).first()
        if not emp:
            continue
        for wh in weeks.values():
            if wh >= threshold:
                total_labor_cost += (wh / 5) * emp.hourly_wage

    return {
        "year": year,
        "month": month,
        "total_schedules": total_schedules,
        "total_hours": total_hours,
        "total_labor_cost": round(total_labor_cost),
        "holiday_risk_count": holiday_risk_count,
        "understaffed_slots": understaffed_count,
    }
