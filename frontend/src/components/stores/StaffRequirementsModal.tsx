import { useState, useEffect, useRef } from 'react';
import type { Store, DayOfWeek } from '../../types';
import { DAY_LABELS, DAY_ORDER } from '../../types';
import { api } from '../../services/api';
import TimeSelect from '../TimeSelect';
import '../../components/employees/EmployeeModal.css';
import './StaffRequirementsModal.css';

let _localIdCounter = 0;

interface Slot {
  _localId: number;
  day_of_week: DayOfWeek;
  start_time: string;
  end_time: string;
  required_count: number;
}

interface Props { store: Store; year: number; month: number; allStores: Store[]; onClose: () => void; }

const ACTIVE_DAY_INIT: DayOfWeek = 'MON';

function withLocalId(item: Omit<Slot, '_localId'>): Slot {
  return { ...item, _localId: ++_localIdCounter };
}

export default function StaffRequirementsModal({ store, year, month, allStores, onClose }: Props) {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [activeDay, setActiveDay] = useState<DayOfWeek>(ACTIVE_DAY_INIT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [showDayCopy, setShowDayCopy] = useState(false);
  const [copyTargets, setCopyTargets] = useState<DayOfWeek[]>([]);
  const [copyFrom, setCopyFrom] = useState('');
  const mouseDownRef = useRef<EventTarget | null>(null);

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const res = await api.get(`/stores/${store.id}/requirements/${year}/${month}`);
      const seen = new Set<string>();
      const deduped: Slot[] = [];
      for (const item of res.data) {
        const key = `${item.day_of_week}|${item.start_time}|${item.end_time}`;
        if (seen.has(key)) continue;
        seen.add(key);
        deduped.push(withLocalId({
          day_of_week: item.day_of_week,
          start_time: item.start_time,
          end_time: item.end_time,
          required_count: item.required_count,
        }));
      }
      setSlots(deduped);
    } finally { setLoading(false); }
  }

  const daySlots = slots
    .filter((s) => s.day_of_week === activeDay)
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

  function addSlot() {
    setSlots((prev) => [...prev, withLocalId({
      day_of_week: activeDay, start_time: '10:00', end_time: '14:00', required_count: 2,
    })]);
  }

  function updateSlot(localId: number, field: keyof Omit<Slot, '_localId'>, value: any) {
    setSlots((prev) => prev.map((s) => s._localId === localId ? { ...s, [field]: value } : s));
  }

  function removeSlot(localId: number) {
    setSlots((prev) => prev.filter((s) => s._localId !== localId));
  }

  function handleDayCopy() {
    if (copyTargets.length === 0) return;
    const src = slots.filter((s) => s.day_of_week === activeDay);
    const overwriteDays = copyTargets.filter((d) => slots.some((s) => s.day_of_week === d));
    if (overwriteDays.length > 0) {
      const names = overwriteDays.map((d) => DAY_LABELS[d]).join(', ');
      if (!confirm(`${names}요일에 기존 설정이 있습니다. 덮어쓰시겠습니까?`)) return;
    }
    setSlots((prev) => [
      ...prev.filter((s) => !copyTargets.includes(s.day_of_week)),
      ...copyTargets.flatMap((d) => src.map((s) => withLocalId({ ...s, day_of_week: d }))),
    ]);
    setShowDayCopy(false);
    setCopyTargets([]);
  }

  function toggleCopyTarget(day: DayOfWeek) {
    setCopyTargets((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
  }

  async function handleSave() {
    setSaving(true); setError('');
    try {
      const items = slots.map(({ day_of_week, start_time, end_time, required_count }) => ({
        day_of_week, start_time, end_time, required_count,
      }));
      await api.put(`/stores/${store.id}/requirements/${year}/${month}`, { items });
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
            <h2 className="modal-title">{store.name} — {year}년 {month}월 필요인원</h2>
            <p className="modal-subtitle">요일·시간대별 필요 인원수를 설정합니다.</p>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {/* 다른 매장/달 복사 */}
          <div className="req-copy-bar">
            <span className="req-copy-label">다른 달·매장에서 복사:</span>
            <select className="emp-month-select" value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
              <option value="">선택...</option>
              {allStores.map((s) => [-2, -1, 0].map((mo) => {
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
              불러오기
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
                {daySlots.map((slot) => (
                  <div key={slot._localId} className="req-slot-row">
                    <TimeSelect
                      value={slot.start_time}
                      onChange={(v) => updateSlot(slot._localId, 'start_time', v)}
                    />
                    <span className="req-tilde">~</span>
                    <TimeSelect
                      value={slot.end_time}
                      onChange={(v) => updateSlot(slot._localId, 'end_time', v)}
                    />
                    <span className="req-count-label">필요인원</span>
                    <input type="number" className="req-count-input" min={0} max={20}
                      value={slot.required_count}
                      onChange={(e) => updateSlot(slot._localId, 'required_count', Number(e.target.value))} />
                    <span className="req-count-label">명</span>
                    <button className="btn btn--danger btn--sm" onClick={() => removeSlot(slot._localId)}>삭제</button>
                  </div>
                ))}
              </div>

              <div className="req-actions">
                <button className="btn btn--secondary btn--sm" onClick={addSlot}>+ 시간대 추가</button>
                <button className="btn btn--ghost btn--sm" onClick={() => { setShowDayCopy(!showDayCopy); setCopyTargets([]); }}>
                  {DAY_LABELS[activeDay]}요일 → 다른 요일 복사
                </button>
              </div>

              {showDayCopy && (
                <div className="req-day-copy-panel">
                  <p className="req-day-copy-label">복사할 대상 요일 선택 (복수 선택 가능):</p>
                  <div className="req-day-copy-checks">
                    {DAY_ORDER.filter((d) => d !== activeDay).map((d) => (
                      <label key={d} className="req-day-copy-check">
                        <input
                          type="checkbox"
                          checked={copyTargets.includes(d)}
                          onChange={() => toggleCopyTarget(d)}
                        />
                        {DAY_LABELS[d]}
                      </label>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    <button
                      className="btn btn--primary btn--sm"
                      onClick={handleDayCopy}
                      disabled={copyTargets.length === 0}
                    >
                      {copyTargets.map((d) => DAY_LABELS[d]).join(', ')}요일로 복사
                    </button>
                    <button className="btn btn--secondary btn--sm" onClick={() => { setShowDayCopy(false); setCopyTargets([]); }}>
                      취소
                    </button>
                  </div>
                </div>
              )}
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
