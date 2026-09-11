import { useState, useEffect } from 'react';
import type { Employee, DayOfWeek } from '../../types';
import { DAY_LABELS, DAY_ORDER } from '../../types';
import { api } from '../../services/api';
import './WorkPatternModal.css';
import './AvailabilityModal.css';

interface DayRow {
  day_of_week: DayOfWeek;
  is_day_unavailable: boolean;
  unavailable_start: string;
  unavailable_end: string;
  memo: string;
}

interface Exception {
  id?: number;
  exception_date: string;
  is_day_unavailable: boolean;
  unavailable_start: string;
  unavailable_end: string;
  memo: string;
}

interface Props {
  employee: Employee;
  year: number;
  month: number;
  onClose: () => void;
}

function defaultRows(): DayRow[] {
  return DAY_ORDER.map((d) => ({
    day_of_week: d,
    is_day_unavailable: false,
    unavailable_start: '',
    unavailable_end: '',
    memo: '',
  }));
}

export default function AvailabilityModal({ employee, year, month, onClose }: Props) {
  const [rows, setRows] = useState<DayRow[]>(defaultRows());
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [newEx, setNewEx] = useState<Exception>({
    exception_date: '', is_day_unavailable: false,
    unavailable_start: '', unavailable_end: '', memo: '',
  });

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [avRes, exRes] = await Promise.all([
        api.get(`/employees/${employee.id}/availability/${year}/${month}`),
        api.get(`/employees/${employee.id}/exceptions/${year}/${month}`),
      ]);
      const avData = avRes.data;
      setRows(DAY_ORDER.map((d) => {
        const found = avData.find((r: any) => r.day_of_week === d);
        return {
          day_of_week: d,
          is_day_unavailable: found?.is_day_unavailable ?? false,
          unavailable_start: found?.unavailable_start ?? '',
          unavailable_end: found?.unavailable_end ?? '',
          memo: found?.memo ?? '',
        };
      }));
      setExceptions(exRes.data.map((e: any) => ({
        id: e.id,
        exception_date: e.exception_date,
        is_day_unavailable: e.is_day_unavailable,
        unavailable_start: e.unavailable_start ?? '',
        unavailable_end: e.unavailable_end ?? '',
        memo: e.memo ?? '',
      })));
    } finally {
      setLoading(false);
    }
  }

  function updateRow(day: DayOfWeek, field: keyof DayRow, value: any) {
    setRows((prev) => prev.map((r) => r.day_of_week === day ? { ...r, [field]: value } : r));
  }

  async function handleSave() {
    setSaving(true); setError('');
    try {
      await api.put(`/employees/${employee.id}/availability/${year}/${month}`, {
        days: rows.map((r) => ({
          day_of_week: r.day_of_week,
          is_day_unavailable: r.is_day_unavailable,
          unavailable_start: r.unavailable_start || null,
          unavailable_end: r.unavailable_end || null,
          memo: r.memo || null,
        })),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleAddException() {
    if (!newEx.exception_date) { setError('날짜를 선택해 주세요.'); return; }
    setSaving(true); setError('');
    try {
      await api.post(`/employees/${employee.id}/exceptions`, {
        exception_date: newEx.exception_date,
        is_day_unavailable: newEx.is_day_unavailable,
        unavailable_start: newEx.unavailable_start || null,
        unavailable_end: newEx.unavailable_end || null,
        memo: newEx.memo || null,
      });
      setNewEx({ exception_date: '', is_day_unavailable: false, unavailable_start: '', unavailable_end: '', memo: '' });
      await loadData();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteException(id: number) {
    await api.delete(`/employees/exceptions/${id}`);
    await loadData();
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">{employee.name} — {year}년 {month}월 불가능 시간</h2>
            <p className="modal-subtitle">근무 불가능한 시간을 요일별로 입력합니다. 입력하지 않은 요일은 종일 가능으로 처리됩니다.</p>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {loading ? <p className="wp-loading">불러오는 중...</p> : (
            <>
              {/* 요일별 불가능 시간 */}
              <h3 className="av-section-title">요일별 불가능 시간</h3>
              <table className="wp-table">
                <thead>
                  <tr>
                    <th>요일</th>
                    <th>종일 불가</th>
                    <th>불가 시작</th>
                    <th>불가 종료</th>
                    <th>메모</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.day_of_week} className={row.is_day_unavailable ? 'wp-row--off' : ''}>
                      <td>
                        <span className={`day-badge ${['SAT','SUN'].includes(row.day_of_week) ? 'day-badge--weekend' : ''}`}>
                          {DAY_LABELS[row.day_of_week]}
                        </span>
                      </td>
                      <td className="wp-toggle">
                        <label className="toggle">
                          <input type="checkbox" checked={row.is_day_unavailable}
                            onChange={(e) => updateRow(row.day_of_week, 'is_day_unavailable', e.target.checked)} />
                          <span className="toggle-track" />
                        </label>
                      </td>
                      <td>
                        <input type="time" className="wp-time-input"
                          value={row.unavailable_start} disabled={row.is_day_unavailable}
                          onChange={(e) => updateRow(row.day_of_week, 'unavailable_start', e.target.value)} />
                      </td>
                      <td>
                        <input type="time" className="wp-time-input"
                          value={row.unavailable_end} disabled={row.is_day_unavailable}
                          onChange={(e) => updateRow(row.day_of_week, 'unavailable_end', e.target.value)} />
                      </td>
                      <td>
                        <input className="av-memo-input" value={row.memo}
                          placeholder="메모"
                          onChange={(e) => updateRow(row.day_of_week, 'memo', e.target.value)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* 특정 날짜 예외 */}
              <h3 className="av-section-title" style={{ marginTop: 24 }}>특정 날짜 예외 <span className="av-hint">(요일 설정보다 우선 적용)</span></h3>

              {exceptions.length > 0 && (
                <div className="ex-list">
                  {exceptions.map((ex) => (
                    <div key={ex.id} className="ex-item">
                      <span className="ex-date">{ex.exception_date}</span>
                      <span className="ex-desc">
                        {ex.is_day_unavailable ? '종일 불가능'
                          : `${ex.unavailable_start}~${ex.unavailable_end} 불가능`}
                      </span>
                      {ex.memo && <span className="ex-memo">{ex.memo}</span>}
                      <button className="btn btn--danger btn--sm" onClick={() => handleDeleteException(ex.id!)}>삭제</button>
                    </div>
                  ))}
                </div>
              )}

              <div className="ex-add">
                <input type="date" className="wp-time-input" style={{ width: 140 }}
                  value={newEx.exception_date}
                  onChange={(e) => setNewEx((p) => ({ ...p, exception_date: e.target.value }))} />
                <label className="toggle" style={{ margin: '0 8px' }}>
                  <input type="checkbox" checked={newEx.is_day_unavailable}
                    onChange={(e) => setNewEx((p) => ({ ...p, is_day_unavailable: e.target.checked }))} />
                  <span className="toggle-track" />
                </label>
                <span style={{ fontSize: 13, color: '#8b8fa8', marginRight: 8 }}>종일</span>
                {!newEx.is_day_unavailable && (<>
                  <input type="time" className="wp-time-input" value={newEx.unavailable_start}
                    onChange={(e) => setNewEx((p) => ({ ...p, unavailable_start: e.target.value }))} />
                  <span style={{ margin: '0 6px', color: '#8b8fa8' }}>~</span>
                  <input type="time" className="wp-time-input" value={newEx.unavailable_end}
                    onChange={(e) => setNewEx((p) => ({ ...p, unavailable_end: e.target.value }))} />
                </>)}
                <button className="btn btn--primary btn--sm" style={{ marginLeft: 8 }}
                  onClick={handleAddException} disabled={saving}>추가</button>
              </div>

              {error && <p className="form-error">{error}</p>}
            </>
          )}
        </div>

        <div className="modal-footer">
          {saved && <span className="save-ok">✅ 저장되었습니다</span>}
          <button className="btn btn--secondary" onClick={onClose}>닫기</button>
          <button className="btn btn--primary" onClick={handleSave} disabled={saving || loading}>
            {saving ? '저장 중...' : '요일별 설정 저장'}
          </button>
        </div>
      </div>
    </div>
  );
}
