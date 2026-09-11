import { useState } from 'react';
import type { Store } from '../../types';
import { scheduleApi } from '../../services/api';
import '../../components/employees/EmployeeModal.css';

interface ScheduleEntry {
  id: number; employee_name: string; store_id: number; store_name: string;
  work_date: string; start_time: string; end_time: string;
  break_minutes: number; status: string; memo?: string;
}

interface Props {
  schedule: ScheduleEntry; stores: Store[];
  onClose: () => void; onSaved: () => void;
}

const REASONS = ['개인사정','결근','대체근무','매장변경','시간변경','관리자수정','기타'];

export default function ScheduleEditModal({ schedule, stores, onClose, onSaved }: Props) {
  const [form, setForm] = useState({
    start_time: schedule.start_time,
    end_time: schedule.end_time,
    store_id: schedule.store_id,
    break_minutes: schedule.break_minutes,
    status: schedule.status,
    change_reason: '관리자수정',
    memo: schedule.memo ?? '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  function handle(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: name === 'store_id' || name === 'break_minutes' ? Number(value) : value }));
    setError('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (form.start_time >= form.end_time) { setError('종료 시간은 시작 시간보다 늦어야 합니다.'); return; }
    setSaving(true);
    try {
      await scheduleApi.update(schedule.id, form);
      onSaved();
    } catch (err: any) { setError(err.message); }
    finally { setSaving(false); }
  }

  const paidMin = Math.max(0,
    (Number(form.end_time.split(':')[0]) * 60 + Number(form.end_time.split(':')[1])) -
    (Number(form.start_time.split(':')[0]) * 60 + Number(form.start_time.split(':')[1])) -
    form.break_minutes
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">스케줄 수정</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="form-section">
            <p style={{fontSize:14,color:'#8b8fa8',marginBottom:12}}>
              {schedule.employee_name} · {schedule.work_date}
            </p>
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
              <div className="form-group">
                <label>배정 매장</label>
                <select name="store_id" value={form.store_id} onChange={handle}>
                  {stores.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>상태</label>
                <select name="status" value={form.status} onChange={handle}>
                  <option value="DRAFT">작성 중</option>
                  <option value="CONFIRMED">확정</option>
                  <option value="LOCKED">잠금</option>
                </select>
              </div>
              <div className="form-group">
                <label>변경 사유</label>
                <select name="change_reason" value={form.change_reason} onChange={handle}>
                  {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>
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
              {saving ? '저장 중...' : '수정 완료'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
