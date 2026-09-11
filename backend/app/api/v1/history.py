import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date

from app.database.database import get_db
from app.models.models import ScheduleHistory, Schedule, Employee, Store

router = APIRouter(tags=["변경 이력"])


def _parse_json(s):
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {"raw": str(s)}


@router.get("/history/{year}/{month}")
def get_history(year: int, month: int, db: Session = Depends(get_db)):
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    history = (
        db.query(ScheduleHistory)
        .join(Schedule, ScheduleHistory.schedule_id == Schedule.id)
        .filter(Schedule.work_date >= start, Schedule.work_date < end)
        .order_by(ScheduleHistory.changed_at.desc())
        .all()
    )

    result = []
    for h in history:
        sch = db.query(Schedule).filter_by(id=h.schedule_id).first()
        emp = db.query(Employee).filter_by(id=sch.employee_id).first() if sch else None
        store = db.query(Store).filter_by(id=sch.store_id).first() if sch else None
        result.append({
            "id": h.id,
            "schedule_id": h.schedule_id,
            "employee_name": emp.name if emp else "알 수 없음",
            "store_name": store.name if store else "알 수 없음",
            "work_date": sch.work_date.isoformat() if sch else "",
            "change_reason": h.change_reason.value if hasattr(h.change_reason, 'value') else str(h.change_reason),
            "changed_by": h.changed_by or "관리자",
            "changed_at": h.changed_at.isoformat() if h.changed_at else "",
            "before_data": _parse_json(h.before_data),
            "after_data": _parse_json(h.after_data),
        })
    return result
