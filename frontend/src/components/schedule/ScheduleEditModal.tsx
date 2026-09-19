import { useState, useRef } from 'react';
import type { Store } from '../../types';
import { scheduleApi } from '../../services/api';
import '../../components/employees/EmployeeModal.css';

interface ScheduleEntry {
  id: number; employee_id: number; employee_name: string; store_id: number; store_name: string;
  work_date: string; start_time: string; end_time: string;
  break_minutes: number; status: string; memo?: string;
}

interface EmployeeOption {
  id: number; name: string; employee_type: string;
}

interface Props {
  schedule: ScheduleEntry | null;  // null = 추가 모드
  stores: Store[];
  employees?: EmployeeOption[];
  defaultDate?: string;
  onClose: () => void;
  onSaved: () => void;
}

const REASONS = ['개인사정','결근','대체근무','매장변경','시간변경','관리자수정','기타'];

export default function ScheduleEditModal({ schedule, stores, employees = [], defaultDate, onClose, onSaved }: Props) {
  const isCreate = schedule === null;
  const today = new Date().toISOString().slice(0, 10);

  const [form, setForm] = useState({
    employee_id: schedule?.employee_id ?? (employees[0]?.id ?? 0),
    work_date: schedule?.work_date ?? (defaultDate ?? today),
    start_time: schedule?.start_time ?? '09:00',
    end_time: schedule?.end_time ?? '18:00',
    store_id: schedule?.store_id ?? (stores[0]?.id ?? 0),
    break_minutes: schedule?.break_minutes ?? 0,
    status: schedule?.status ?? 'DRAFT',
    change_reason: '관리자수정',
    memo: schedule?.memo ?? '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const mouseDownRef = useRef<EventTarget | null>(null);

  function handle(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value } = e.target;
    setForm((p) => ({
      ...p,
      [name]: (name === 'store_id' || name === 'break_minutes' || name === 'employee_id')
        ? Number(value)
        : value,
    }));
    setError('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (form.start_time >= form.end_time) {
      setError('종료 시간은 시작 시간보다 늦어야 합니다.');
      return;
    }
    if (!form.employee_id || !form.store_id) {
      setError('직원과 매장을 선택해주세요.');
      return;
    }
    setSaving(true);
    try {
      if (isCreate) {
        await scheduleApi.create({
          employee_id: form.employee_id,
          store_id: form.store_id,
          work_date: form.work_date,
          start_time: form.start_time,
          end_time: form.end_time,
          break_minutes: form.break_minutes,
          memo: form.memo || null,
        });
      } else {
        await scheduleApi.update(schedule!.id, form);
      }
      onSaved();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const paidMin = Math.max(0,
    (Number(form.end_time.split(':')[0]) * 60 + Number(form.end_time.split(':')[1])) -
    (Number(form.start_time.split(':')[0]) * 60 + Number(form.start_time.split(':')[1])) -
    form.break_minutes
  );

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => { mouseDownRef.current = e.target; }}
      onClick={(e) => {
        if (mouseDownRef.current === e.currentTarget) onClose();
        mouseDownRef.current = null;
      }}
    >
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{isCreate ? '스케줄 추가' : '스케줄 수정'}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="form-section">
            {/* 직원 선택 */}
            {(isCreate || employees.length > 0) ? (
              <div className="form-group">
                <label>직원</label>
                <select name="employee_id" value={form.employee_id} onChange={handle}>
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.name} ({emp.employee_type === 'REGULAR' ? '정규직' : '파트타이머'})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <p style={{fontSize:14,color:'#8b8fa8',marginBottom:12}}>
                직원: {schedule?.employee_name}
              </p>
            )}

            <div className="form-row">
              <div className="form-group">
                <label>근무일</label>
                <input type="date" name="work_date" value={form.work_date} onChange={handle} />
              </div>
              <div className="form-group">
                <label>배정 매장</label>
                <select name="store_id" value={form.store_id} onChange={handle}>
                  {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>시작 시간</label>
                <input type="time" name="start_time" value={form.start_time} onChange={handle} />
              </div>
              <div className="form-group">
                <label>종료 시간</label>
                <input type="time" name="end_time" value={form.end_time} onChange={handle} />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>휴게시간 (분)</label>
                <input type="number" name="break_minutes" value={form.break_minutes} onChange={handle} min={0} />
              </div>
              {!isCreate ? (
                <div className="form-group">
                  <label>상태</label>
                  <select name="status" value={form.status} onChange={handle}>
                    <option value="DRAFT">작성 중</option>
                    <option value="CONFIRMED">확정</option>
                    <option value="LOCKED">잠금</option>
                  </select>
                </div>
              ) : (
                <div className="form-group" />
              )}
            </div>

            {!isCreate && (
              <div className="form-row">
                <div className="form-group">
                  <label>변경 사유</label>
                  <select name="change_reason" value={form.change_reason} onChange={handle}>
                    {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div className="form-group" />
              </div>
            )}

            <div className="form-group">
              <label>메모</label>
              <textarea name="memo" value={form.memo} onChange={handle} rows={2} />
            </div>

            <p style={{fontSize:13,color:'#4f7cff',marginTop:8}}>
              유급 근무시간: {Math.floor(paidMin/60)}시간 {paidMin%60}분
            </p>
          </div>

          {error && <p className="form-error">{error}</p>}

          <div className="modal-footer">
            <button type="button" className="btn btn--secondary" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn--primary" disabled={saving}>
              {saving ? (isCreate ? '추가 중...' : '저장 중...') : (isCreate ? '스케줄 추가' : '수정 완료')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
