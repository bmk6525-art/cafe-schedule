import { useState, useEffect, useRef } from 'react';
import type { Employee, Store, DayOfWeek } from '../../types';
import { DAY_LABELS, DAY_ORDER } from '../../types';
import { api } from '../../services/api';
import TimeSelect from '../TimeSelect';
import './WorkPatternModal.css';
import './AvailabilityModal.css';

// 요일별 가능/불가능 설정을 하나의 행으로 관리
interface DayRow {
  day_of_week: DayOfWeek;
  // 가능 설정
  is_working_day: boolean;
  store_id: number | null;
  available_start: string;
  available_end: string;
  // 불가능 설정
  is_day_unavailable: boolean;
  unavailable_start: string;
  unavailable_end: string;
  memo: string;
}

interface Exception {
  id?: number;
  exception_date: string;
  is_day_unavailable: boolean;
  is_available_override: boolean;
  unavailable_start: string;
  unavailable_end: string;
  memo: string;
}

interface Props {
  employee: Employee;
  year: number;
  month: number;
  stores: Store[];
  onSaved: (availableCount: number, unavailableCount: number) => void;
  onClose: () => void;
}

function defaultRows(): DayRow[] {
  return DAY_ORDER.map((d) => ({
    day_of_week: d,
    is_working_day: false,
    store_id: null,
    available_start: '',
    available_end: '',
    is_day_unavailable: false,
    unavailable_start: '',
    unavailable_end: '',
    memo: '',
  }));
}

const EMPTY_NEW_EX: Exception = {
  exception_date: '', is_day_unavailable: false, is_available_override: false,
  unavailable_start: '09:00', unavailable_end: '18:00', memo: '',
};

export default function AvailabilityModal({ employee, year, month, stores, onSaved, onClose }: Props) {
  const [rows, setRows] = useState<DayRow[]>(defaultRows());
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [newEx, setNewEx] = useState<Exception>(EMPTY_NEW_EX);
  const mouseDownRef = useRef<EventTarget | null>(null);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [avRes, exRes] = await Promise.all([
        api.get(`/employees/${employee.id}/availability/${year}/${month}`),
        api.get(`/employees/${employee.id}/exceptions/${year}/${month}`),
      ]);
      const avData: any[] = avRes.data;

      // AVAILABLE / UNAVAILABLE 레코드를 요일별로 병합
      // entry_type === 'AVAILABLE'이 우선, 없으면 is_working_day/available_start 필드로 판별 (구 DB 호환)
      setRows(DAY_ORDER.map((d) => {
        const allForDay = avData.filter((r: any) => r.day_of_week === d);
        const avail = allForDay.find((r: any) =>
          r.entry_type === 'AVAILABLE' ||
          (!r.entry_type && (r.is_working_day || r.available_start))
        );
        const unavail = allForDay.find((r: any) =>
          r !== avail && (r.entry_type === 'UNAVAILABLE' || r.is_day_unavailable || r.unavailable_start)
        );
        return {
          day_of_week: d,
          is_working_day: avail?.is_working_day ?? false,
          store_id: avail?.store_id ?? null,
          available_start: avail?.available_start ?? '',
          available_end: avail?.available_end ?? '',
          is_day_unavailable: unavail?.is_day_unavailable ?? false,
          unavailable_start: unavail?.unavailable_start ?? '',
          unavailable_end: unavail?.unavailable_end ?? '',
          memo: avail?.memo ?? unavail?.memo ?? '',
        };
      }));
      setExceptions(_parseExceptions(exRes.data));
    } catch (e: any) {
      setError(`데이터 로드 실패: ${e?.response?.data?.detail ?? e?.message ?? '알 수 없는 오류'}`);
    } finally {
      setLoading(false);
    }
  }

  // 예외만 다시 불러옴 — 요일별 설정(rows)은 건드리지 않음
  async function loadExceptions() {
    try {
      const exRes = await api.get(`/employees/${employee.id}/exceptions/${year}/${month}`);
      setExceptions(_parseExceptions(exRes.data));
    } catch { /* ignore */ }
  }

  function _parseExceptions(data: any[]): Exception[] {
    return data.map((e: any) => ({
      id: e.id,
      exception_date: e.exception_date,
      is_day_unavailable: e.is_day_unavailable,
      is_available_override: e.is_available_override ?? false,
      unavailable_start: e.unavailable_start ?? '',
      unavailable_end: e.unavailable_end ?? '',
      memo: e.memo ?? '',
    }));
  }

  function updateRow(day: DayOfWeek, field: keyof DayRow, value: any) {
    setRows((prev) => prev.map((r) => {
      if (r.day_of_week !== day) return r;
      const updated = { ...r, [field]: value };
      // 종일 불가능 체크 시 시간 초기화
      if (field === 'is_day_unavailable' && value) {
        updated.unavailable_start = '';
        updated.unavailable_end = '';
      }
      return updated;
    }));
  }

  async function handleSave() {
    setSaving(true); setError('');
    try {
      await api.put(`/employees/${employee.id}/availability/${year}/${month}`, {
        days: rows.map((r) => ({
          day_of_week: r.day_of_week,
          is_working_day: r.is_working_day,
          store_id: r.store_id ?? null,
          available_start: r.available_start || null,
          available_end: r.available_end || null,
          is_day_unavailable: r.is_day_unavailable,
          unavailable_start: r.unavailable_start || null,
          unavailable_end: r.unavailable_end || null,
          memo: r.memo || null,
        })),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onSaved(availCount, unavailCount);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleAddException() {
    if (!newEx.exception_date) { setError('날짜를 선택해 주세요.'); return; }
    if (newEx.is_available_override && (!newEx.unavailable_start || !newEx.unavailable_end)) {
      setError('가능 시간대의 시작/종료를 입력해 주세요.'); return;
    }
    setSaving(true); setError('');
    try {
      await api.post(`/employees/${employee.id}/exceptions`, {
        exception_date: newEx.exception_date,
        is_day_unavailable: newEx.is_available_override ? false : newEx.is_day_unavailable,
        is_available_override: newEx.is_available_override,
        unavailable_start: (newEx.is_available_override || !newEx.is_day_unavailable)
          ? newEx.unavailable_start || null : null,
        unavailable_end: (newEx.is_available_override || !newEx.is_day_unavailable)
          ? newEx.unavailable_end || null : null,
        memo: newEx.memo || null,
      });
      setNewEx(EMPTY_NEW_EX);
      await loadExceptions();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteException(id: number) {
    await api.delete(`/employees/exceptions/${id}`);
    await loadExceptions();
  }

  function exDesc(ex: Exception) {
    if (ex.is_available_override) {
      if (ex.unavailable_start && ex.unavailable_end)
        return `${ex.unavailable_start}~${ex.unavailable_end} 만 가능`;
      return '종일 가능';
    }
    if (ex.is_day_unavailable) return '종일 불가능';
    if (ex.unavailable_start && ex.unavailable_end)
      return `${ex.unavailable_start}~${ex.unavailable_end} 불가능`;
    return '불가능';
  }

  // 가능/불가능 설정 유무 카운트 (저장 버튼 위 상태 표시용)
  const availCount = rows.filter((r) => r.is_working_day || r.available_start).length;
  const unavailCount = rows.filter((r) => r.is_day_unavailable || r.unavailable_start).length;

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
            <h2 className="modal-title">{employee.name} — {year}년 {month}월 근무 가용성</h2>
            <p className="modal-subtitle">요일별 근무 가능/불가능 시간을 설정합니다. 불가능 설정이 가능 설정보다 우선합니다.</p>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {loading ? <p className="wp-loading">불러오는 중...</p> : (
            <>
              {/* 요일별 가능/불가능 시간 통합 테이블 */}
              <table className="wp-table av-table-new">
                <thead>
                  <tr>
                    <th rowSpan={2} className="av-th-day">요일</th>
                    <th colSpan={4} className="av-th-avail">근무 가능</th>
                    <th colSpan={3} className="av-th-unavail">근무 불가능</th>
                    <th rowSpan={2}>메모</th>
                  </tr>
                  <tr>
                    <th className="av-th-sub">가능 요일</th>
                    <th className="av-th-sub">호점</th>
                    <th className="av-th-sub">가능 시작</th>
                    <th className="av-th-sub">가능 종료</th>
                    <th className="av-th-sub">종일 불가</th>
                    <th className="av-th-sub">불가 시작</th>
                    <th className="av-th-sub">불가 종료</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const isAvail = row.is_working_day || !!row.available_start;
                    const isUnavail = row.is_day_unavailable || !!row.unavailable_start;
                    const rowClass = [
                      isAvail && !isUnavail ? 'av-row--avail' : '',
                      isUnavail && !isAvail ? 'av-row--unavail' : '',
                      isAvail && isUnavail ? 'av-row--both' : '',
                    ].filter(Boolean).join(' ');
                    return (
                      <tr key={row.day_of_week} className={rowClass}>
                        <td>
                          <span className={`day-badge ${['SAT','SUN'].includes(row.day_of_week) ? 'day-badge--weekend' : ''}`}>
                            {DAY_LABELS[row.day_of_week]}
                          </span>
                        </td>
                        {/* 가능 설정 */}
                        <td className="wp-toggle">
                          <label className="toggle">
                            <input
                              type="checkbox"
                              checked={row.is_working_day}
                              onChange={(e) => updateRow(row.day_of_week, 'is_working_day', e.target.checked)}
                            />
                            <span className="toggle-track toggle-track--avail" />
                          </label>
                        </td>
                        {/* 호점 선택 */}
                        <td className="av-td-store">
                          {row.is_working_day || row.available_start ? (
                            <select
                              className="av-store-select"
                              value={row.store_id ?? ''}
                              onChange={(e) => updateRow(row.day_of_week, 'store_id', e.target.value ? Number(e.target.value) : null)}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <option value="">전체</option>
                              {stores.map((s) => (
                                <option key={s.id} value={s.id}>{s.name}</option>
                              ))}
                            </select>
                          ) : (
                            <span className="av-time-na">—</span>
                          )}
                        </td>
                          {/* 가능 시작 */}
                        <td className="av-td-time">
                          {row.available_start ? (
                            <div className="av-time-wrap">
                              <TimeSelect
                                value={row.available_start}
                                onChange={(v) => updateRow(row.day_of_week, 'available_start', v)}
                              />
                              <button
                                className="av-clear-btn"
                                onClick={() => {
                                  updateRow(row.day_of_week, 'available_start', '');
                                  updateRow(row.day_of_week, 'available_end', '');
                                }}
                                title="시간 지우기"
                              >×</button>
                            </div>
                          ) : (
                            <button
                              className="av-set-btn"
                              onClick={() => updateRow(row.day_of_week, 'available_start', '09:00')}
                            >+ 시간</button>
                          )}
                        </td>
                        {/* 가능 종료 */}
                        <td className="av-td-time">
                          {row.available_start ? (
                            row.available_end ? (
                              <div className="av-time-wrap">
                                <TimeSelect
                                  value={row.available_end}
                                  onChange={(v) => updateRow(row.day_of_week, 'available_end', v)}
                                />
                                <button
                                  className="av-close-btn"
                                  onClick={() => updateRow(row.day_of_week, 'available_end', '')}
                                  title="마감까지로 변경"
                                >마감</button>
                              </div>
                            ) : (
                              <button
                                className="av-until-close"
                                onClick={() => updateRow(row.day_of_week, 'available_end', '18:00')}
                                title="클릭하면 종료 시간 직접 설정"
                              >마감까지 ✎</button>
                            )
                          ) : <span className="av-time-na">—</span>}
                        </td>
                        {/* 불가능 설정 */}
                        <td className="wp-toggle">
                          <label className="toggle">
                            <input
                              type="checkbox"
                              checked={row.is_day_unavailable}
                              onChange={(e) => updateRow(row.day_of_week, 'is_day_unavailable', e.target.checked)}
                            />
                            <span className="toggle-track" />
                          </label>
                        </td>
                        {/* 불가능 시작 */}
                        <td className="av-td-time">
                          {row.is_day_unavailable ? (
                            <span className="av-time-na">종일</span>
                          ) : row.unavailable_start ? (
                            <div className="av-time-wrap">
                              <TimeSelect
                                value={row.unavailable_start}
                                onChange={(v) => updateRow(row.day_of_week, 'unavailable_start', v)}
                              />
                              <button
                                className="av-clear-btn"
                                onClick={() => {
                                  updateRow(row.day_of_week, 'unavailable_start', '');
                                  updateRow(row.day_of_week, 'unavailable_end', '');
                                }}
                                title="시간 지우기"
                              >×</button>
                            </div>
                          ) : (
                            <button
                              className="av-set-btn av-set-btn--unavail"
                              onClick={() => updateRow(row.day_of_week, 'unavailable_start', '13:00')}
                            >+ 시간</button>
                          )}
                        </td>
                        {/* 불가능 종료 */}
                        <td className="av-td-time">
                          {row.is_day_unavailable ? (
                            <span className="av-time-na">종일</span>
                          ) : row.unavailable_start ? (
                            row.unavailable_end ? (
                              <div className="av-time-wrap">
                                <TimeSelect
                                  value={row.unavailable_end}
                                  onChange={(v) => updateRow(row.day_of_week, 'unavailable_end', v)}
                                />
                                <button
                                  className="av-close-btn av-close-btn--unavail"
                                  onClick={() => updateRow(row.day_of_week, 'unavailable_end', '')}
                                  title="마감까지로 변경"
                                >마감</button>
                              </div>
                            ) : (
                              <button
                                className="av-until-close av-until-close--unavail"
                                onClick={() => updateRow(row.day_of_week, 'unavailable_end', '18:00')}
                                title="클릭하면 종료 시간 직접 설정"
                              >마감까지 ✎</button>
                            )
                          ) : <span className="av-time-na">—</span>}
                        </td>
                        <td>
                          <input
                            className="av-memo-input" value={row.memo}
                            placeholder="메모"
                            onChange={(e) => updateRow(row.day_of_week, 'memo', e.target.value)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* 입력 가이드 */}
              <div className="av-guide">
                <span className="av-guide-item av-guide-item--avail">■ 가능 요일 설정</span>
                <span className="av-guide-item av-guide-item--unavail">■ 불가능 설정</span>
                <span className="av-guide-item av-guide-item--both">■ 가능+불가능 동시 (불가능 우선)</span>
                <span className="av-guide-hint">가능 시간 미입력 시 해당 요일 전체 가능</span>
              </div>

              {/* 특정 날짜 예외 */}
              <h3 className="av-section-title" style={{ marginTop: 24 }}>
                특정 날짜 예외 <span className="av-hint">(요일 설정보다 우선 적용)</span>
              </h3>

              {exceptions.length > 0 && (
                <div className="ex-list">
                  {exceptions.map((ex) => (
                    <div key={ex.id} className="ex-item">
                      <span className="ex-date">{ex.exception_date}</span>
                      <span className={`ex-badge ${ex.is_available_override ? 'ex-badge--avail' : 'ex-badge--unavail'}`}>
                        {ex.is_available_override ? '가능' : '불가능'}
                      </span>
                      <span className="ex-desc">{exDesc(ex)}</span>
                      {ex.memo && <span className="ex-memo">{ex.memo}</span>}
                      <button className="btn btn--danger btn--sm" onClick={() => handleDeleteException(ex.id!)}>삭제</button>
                    </div>
                  ))}
                </div>
              )}

              {/* 예외 추가 폼 */}
              <div className="ex-add">
                <input type="date" className="wp-time-input" style={{ width: 140 }}
                  value={newEx.exception_date}
                  onChange={(e) => setNewEx((p) => ({ ...p, exception_date: e.target.value }))} />

                <select
                  className="ex-type-select"
                  value={newEx.is_available_override ? 'avail' : 'unavail'}
                  onChange={(e) => setNewEx((p) => ({
                    ...p,
                    is_available_override: e.target.value === 'avail',
                    is_day_unavailable: false,
                  }))}
                  onClick={(e) => e.stopPropagation()}
                >
                  <option value="unavail">불가능</option>
                  <option value="avail">가능 (예외)</option>
                </select>

                {!newEx.is_available_override && (
                  <>
                    <label className="toggle" style={{ margin: '0 8px' }}>
                      <input type="checkbox" checked={newEx.is_day_unavailable}
                        onChange={(e) => setNewEx((p) => ({ ...p, is_day_unavailable: e.target.checked }))} />
                      <span className="toggle-track" />
                    </label>
                    <span style={{ fontSize: 13, color: '#8b8fa8', marginRight: 8 }}>종일</span>
                  </>
                )}

                {(newEx.is_available_override || !newEx.is_day_unavailable) && (
                  <>
                    <TimeSelect
                      value={newEx.unavailable_start || '09:00'}
                      onChange={(v) => setNewEx((p) => ({ ...p, unavailable_start: v }))}
                    />
                    <span style={{ margin: '0 6px', color: '#8b8fa8' }}>~</span>
                    <TimeSelect
                      value={newEx.unavailable_end || '18:00'}
                      onChange={(v) => setNewEx((p) => ({ ...p, unavailable_end: v }))}
                    />
                    {newEx.is_available_override && (
                      <span className="ex-avail-hint">이 시간대만 근무 가능</span>
                    )}
                  </>
                )}

                <button className="btn btn--primary btn--sm" style={{ marginLeft: 8 }}
                  onClick={handleAddException} disabled={saving}>추가</button>
              </div>

              {error && <p className="form-error">{error}</p>}
            </>
          )}
        </div>

        <div className="modal-footer">
          {(availCount > 0 || unavailCount > 0) && (
            <span className="av-status-summary">
              {availCount > 0 && <span className="av-status-avail">가능 {availCount}개</span>}
              {unavailCount > 0 && <span className="av-status-unavail">불가능 {unavailCount}개</span>}
            </span>
          )}
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
