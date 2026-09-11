import { useState, useEffect } from 'react';
import type { Store, DayOfWeek } from '../../types';
import { DAY_LABELS, DAY_ORDER } from '../../types';
import { api } from '../../services/api';
import '../../components/employees/EmployeeModal.css';
import './StaffRequirementsModal.css';

interface Slot { day_of_week: DayOfWeek; start_time: string; end_time: string; required_count: number; }

interface Props { store: Store; year: number; month: number; allStores: Store[]; onClose: () => void; }

const ACTIVE_DAY_INIT: DayOfWeek = 'MON';

export default function StaffRequirementsModal({ store, year, month, allStores, onClose }: Props) {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [activeDay, setActiveDay] = useState<DayOfWeek>(ACTIVE_DAY_INIT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [copyFrom, setCopyFrom] = useState('');

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const res = await api.get(`/stores/${store.id}/requirements/${year}/${month}`);
      setSlots(res.data);
    } finally { setLoading(false); }
  }

  const daySlots = slots.filter((s) => s.day_of_week === activeDay)
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

  function addSlot() {
    setSlots((prev) => [...prev, { day_of_week: activeDay, start_time: '10:00', end_time: '14:00', required_count: 2 }]);
  }

  function updateSlot(idx: number, field: keyof Slot, value: any) {
    const globalIdx = slots.indexOf(daySlots[idx]);
    setSlots((prev) => prev.map((s, i) => i === globalIdx ? { ...s, [field]: value } : s));
  }

  function removeSlot(idx: number) {
    const globalIdx = slots.indexOf(daySlots[idx]);
    setSlots((prev) => prev.filter((_, i) => i !== globalIdx));
  }

  function copyDayToAll() {
    const src = slots.filter((s) => s.day_of_week === activeDay);
    const others = DAY_ORDER.filter((d) => d !== activeDay);
    setSlots((prev) => [
      ...prev.filter((s) => s.day_of_week === activeDay),
      ...others.flatMap((d) => src.map((s) => ({ ...s, day_of_week: d }))),
    ]);
  }

  async function handleSave() {
    setSaving(true); setError('');
    try {
      await api.put(`/stores/${store.id}/requirements/${year}/${month}`, { items: slots });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) { setError(e.message); }
    finally { setSaving(false); }
  }

  async function handleCopy() {
    if (!copyFrom) return;
    setSaving(true); setError('');
    try {
      const [srcStore, srcYear, srcMonth] = copyFrom.split('-');
      await api.post(
        `/stores/${store.id}/requirements/${year}/${month}/copy-from`,
        null,
        { params: { from_store_id: srcStore, from_year: srcYear, from_month: srcMonth } }
      );
      await loadData();
    } catch (e: any) { setError(e.message); }
    finally { setSaving(false); }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">{store.name} — {year}년 {month}월 필요인원</h2>
            <p className="modal-subtitle">요일·시간대별 필요 인원수를 설정합니다.</p>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {/* 복사 기능 */}
          <div className="req-copy-bar">
            <span className="req-copy-label">복사 가져오기:</span>
            <select className="emp-month-select" value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
              <option value="">선택...</option>
              {allStores.map((s) => [-1, 0].map((mo) => {
                const d = new Date(year, month - 1 + mo);
                return (
                  <option key={`${s.id}-${d.getFullYear()}-${d.getMonth()+1}`}
                    value={`${s.id}-${d.getFullYear()}-${d.getMonth()+1}`}>
                    {s.name} {d.getFullYear()}년 {d.getMonth()+1}월
                  </option>
                );
              }))}
            </select>
            <button className="btn btn--secondary btn--sm" onClick={handleCopy} disabled={!copyFrom || saving}>
              복사
            </button>
          </div>

          {/* 요일 탭 */}
          <div className="req-day-tabs">
            {DAY_ORDER.map((d) => {
              const cnt = slots.filter((s) => s.day_of_week === d).length;
              return (
                <button key={d}
                  className={`req-day-tab ${activeDay === d ? 'req-day-tab--active' : ''}`}
                  onClick={() => setActiveDay(d)}>
                  {DAY_LABELS[d]}
                  {cnt > 0 && <span className="req-slot-count">{cnt}</span>}
                </button>
              );
            })}
          </div>

          {loading ? <p className="wp-loading">불러오는 중...</p> : (
            <>
              <div className="req-slot-list">
                {daySlots.length === 0 && (
                  <p className="req-empty">시간대를 추가하세요.</p>
                )}
                {daySlots.map((slot, i) => (
                  <div key={i} className="req-slot-row">
                    <input type="time" className="wp-time-input" value={slot.start_time}
                      onChange={(e) => updateSlot(i, 'start_time', e.target.value)} />
                    <span className="req-tilde">~</span>
                    <input type="time" className="wp-time-input" value={slot.end_time}
                      onChange={(e) => updateSlot(i, 'end_time', e.target.value)} />
                    <span className="req-count-label">필요인원</span>
                    <input type="number" className="req-count-input" min={0} max={20}
                      value={slot.required_count}
                      onChange={(e) => updateSlot(i, 'required_count', Number(e.target.value))} />
                    <span className="req-count-label">명</span>
                    <button className="btn btn--danger btn--sm" onClick={() => removeSlot(i)}>삭제</button>
                  </div>
                ))}
              </div>

              <div className="req-actions">
                <button className="btn btn--secondary btn--sm" onClick={addSlot}>+ 시간대 추가</button>
                <button className="btn btn--ghost btn--sm" onClick={copyDayToAll}>
                  {DAY_LABELS[activeDay]}요일 설정 → 전체 요일 복사
                </button>
              </div>
            </>
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
