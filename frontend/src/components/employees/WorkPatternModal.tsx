import { useState, useEffect, useRef } from 'react';
import type { Employee, Store, WorkPattern, DayOfWeek } from '../../types';
import { DAY_LABELS, DAY_ORDER } from '../../types';
import { workPatternApi } from '../../services/api';
import TimeSelect from '../TimeSelect';
import './WorkPatternModal.css';

interface Props {
  employee: Employee;
  stores: Store[];
  onClose: () => void;
}

interface PatternRow {
  day_of_week: DayOfWeek;
  is_day_off: boolean;
  start_time: string;
  end_time: string;
  store_id: string;
}

function defaultRows(): PatternRow[] {
  return DAY_ORDER.map((day, i) => ({
    day_of_week: day,
    is_day_off: i >= 5,
    start_time: '09:00',
    end_time: '18:00',
    store_id: '',
  }));
}

export default function WorkPatternModal({ employee, stores, onClose }: Props) {
  const [rows, setRows] = useState<PatternRow[]>(defaultRows());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const mouseDownRef = useRef<EventTarget | null>(null);

  useEffect(() => {
    workPatternApi.get(employee.id)
      .then((res) => {
        const data: WorkPattern[] = res.data;
        if (data.length === 7) {
          setRows(
            DAY_ORDER.map((day) => {
              const p = data.find((d) => d.day_of_week === day);
              return {
                day_of_week: day,
                is_day_off: p?.is_day_off ?? true,
                start_time: p?.start_time ?? '09:00',
                end_time: p?.end_time ?? '18:00',
                store_id: p?.store_id ? String(p.store_id) : '',
              };
            })
          );
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [employee.id]);

  function toggle(day: DayOfWeek) {
    setRows((prev) =>
      prev.map((r) => r.day_of_week === day ? { ...r, is_day_off: !r.is_day_off } : r)
    );
  }

  function updateRow(day: DayOfWeek, field: keyof PatternRow, value: string) {
    setRows((prev) =>
      prev.map((r) => r.day_of_week === day ? { ...r, [field]: value } : r)
    );
  }

  async function handleSave() {
    setSaving(true);
    setError('');
    try {
      const patterns = rows.map((r) => ({
        day_of_week: r.day_of_week,
        is_day_off: r.is_day_off,
        start_time: r.is_day_off ? null : r.start_time,
        end_time: r.is_day_off ? null : r.end_time,
        store_id: r.is_day_off || !r.store_id ? null : Number(r.store_id),
      }));
      await workPatternApi.upsert(employee.id, { patterns });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => { mouseDownRef.current = e.target; }}
      onClick={(e) => {
        if (mouseDownRef.current === e.currentTarget) onClose();
        mouseDownRef.current = null;
      }}
    >
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">{employee.name} — 기본 근무패턴</h2>
            <p className="modal-subtitle">요일별 기본 근무시간과 배정 매장을 설정합니다.</p>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {loading ? (
            <p className="wp-loading">불러오는 중...</p>
          ) : (
            <table className="wp-table">
              <thead>
                <tr>
                  <th>요일</th>
                  <th>휴무</th>
                  <th>시작 시간</th>
                  <th>종료 시간</th>
                  <th>배정 매장</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.day_of_week} className={row.is_day_off ? 'wp-row--off' : ''}>
                    <td className="wp-day">
                      <span className={`day-badge ${['SAT','SUN'].includes(row.day_of_week) ? 'day-badge--weekend' : ''}`}>
                        {DAY_LABELS[row.day_of_week]}
                      </span>
                    </td>
                    <td className="wp-toggle">
                      <label className="toggle">
                        <input
                          type="checkbox"
                          checked={row.is_day_off}
                          onChange={() => toggle(row.day_of_week)}
                        />
                        <span className="toggle-track" />
                      </label>
                    </td>
                    <td>
                      <TimeSelect
                        value={row.start_time}
                        disabled={row.is_day_off}
                        onChange={(v) => updateRow(row.day_of_week, 'start_time', v)}
                      />
                    </td>
                    <td>
                      <TimeSelect
                        value={row.end_time}
                        disabled={row.is_day_off}
                        onChange={(v) => updateRow(row.day_of_week, 'end_time', v)}
                      />
                    </td>
                    <td>
                      <select
                        className="wp-store-select"
                        value={row.store_id}
                        disabled={row.is_day_off}
                        onChange={(e) => updateRow(row.day_of_week, 'store_id', e.target.value)}
                      >
                        <option value="">매장 선택</option>
                        {stores.map((s) => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {error && <p className="form-error">{error}</p>}
        </div>

        <div className="modal-footer">
          {saved && <span className="save-ok">✅ 저장되었습니다</span>}
          <button className="btn btn--secondary" onClick={onClose}>닫기</button>
          <button className="btn btn--primary" onClick={handleSave} disabled={saving || loading}>
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    </div>
  );
}
