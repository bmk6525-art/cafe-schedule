import { useState, useEffect, useMemo, useRef } from 'react';
import html2canvas from 'html2canvas';
import { scheduleApi, storeApi, employeeApi } from '../services/api';
import type { Store } from '../types';
import ScheduleEditModal from '../components/schedule/ScheduleEditModal';
import './Schedule.css';

interface ScheduleEntry {
  id: number; employee_id: number; employee_name: string; employee_type: string;
  store_id: number; store_name: string; work_date: string;
  start_time: string; end_time: string; break_minutes: number;
  status: string; is_cancelled: boolean; memo?: string;
}

interface Issue { type: string; code: string; message: string; schedule_id: number | null; }

type FilterType = 'ALL' | 'REGULAR' | 'PART_TIMER' | string;
type ViewMode = 'week' | 'month';

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

const DAY_KO = ['일', '월', '화', '수', '목', '금', '토'];
const DAY_HEADER = ['월', '화', '수', '목', '금', '토', '일'];

// 캘린더 그리드용 날짜 배열 생성 (월요일 시작, 빈칸 포함)
function buildCalendarGrid(year: number, month: number) {
  const firstDay = new Date(year, month - 1, 1).getDay(); // 0=일
  const total = getDaysInMonth(year, month);
  // 월요일 시작: 일요일(0) → 6, 월(1)→0, ...
  const startOffset = firstDay === 0 ? 6 : firstDay - 1;
  const cells: (number | null)[] = [
    ...Array(startOffset).fill(null),
    ...Array.from({ length: total }, (_, i) => i + 1),
  ];
  // 6행 완성
  while (cells.length % 7 !== 0) cells.push(null);
  // 행으로 나누기
  const rows: (number | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
  return rows;
}

export default function Schedule() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [week, setWeek] = useState(1);
  const [filter, setFilter] = useState<FilterType>('ALL');
  const [viewMode, setViewMode] = useState<ViewMode>('month');

  const [schedules, setSchedules] = useState<ScheduleEntry[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [employees, setEmployees] = useState<{id:number;name:string;employee_type:string}[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [validating, setValidating] = useState(false);
  const [genResult, setGenResult] = useState<{ created: number; warnings: string[] } | null>(null);
  const [editTarget, setEditTarget] = useState<ScheduleEntry | null | 'new'>(null);
  const [addDefaultDate, setAddDefaultDate] = useState('');
  const [calDetailDate, setCalDetailDate] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const calRef = useRef<HTMLDivElement>(null);

  useEffect(() => { loadAll(); }, [year, month]);

  async function loadAll() {
    setLoading(true);
    try {
      const [schRes, storeRes, empRes] = await Promise.all([
        scheduleApi.getAll({ year, month }),
        storeApi.getAll(),
        employeeApi.getAll(),
      ]);
      setSchedules(schRes.data);
      setStores(storeRes.data);
      setEmployees(empRes.data);
    } finally { setLoading(false); }
  }

  async function handleGenerate() {
    if (!confirm(`${year}년 ${month}월 스케줄을 자동 생성합니다.\n기존 DRAFT 스케줄은 삭제됩니다. 계속하시겠습니까?`)) return;
    setGenerating(true); setGenResult(null);
    try {
      const res = await scheduleApi.generate(year, month);
      setGenResult({ created: res.data.created, warnings: res.data.warnings });
      await loadAll();
    } catch (e: any) {
      alert(`스케줄 생성 오류: ${e.message}`);
    } finally { setGenerating(false); }
  }

  async function handleValidate() {
    setValidating(true);
    try {
      const res = await scheduleApi.validate(year, month);
      setIssues(res.data.issues);
    } finally { setValidating(false); }
  }

  async function handleDeduplicate() {
    if (!confirm(`${year}년 ${month}월의 중복 DRAFT 스케줄을 정리합니다. 계속하시겠습니까?`)) return;
    try {
      const res = await scheduleApi.deduplicate(year, month);
      alert(res.data.message);
      await loadAll();
    } catch (e: any) { alert(`오류: ${e.message}`); }
  }

  const [bulkDelConfirm, setBulkDelConfirm] = useState(false);
  async function handleBulkDelete() {
    if (!bulkDelConfirm) { setBulkDelConfirm(true); return; }
    setBulkDelConfirm(false);
    try {
      const res = await scheduleApi.bulkDelete(year, month, false);
      alert(res.data.message);
      await loadAll();
    } catch (e: any) { alert(`오류: ${e.message}`); }
  }

  async function handleSaveImage() {
    if (!calRef.current) return;
    setSaving(true);
    try {
      const canvas = await html2canvas(calRef.current, {
        backgroundColor: '#ffffff',
        scale: 2,
        useCORS: true,
      });
      const link = document.createElement('a');
      link.download = `스케줄_${year}년_${month}월.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } finally { setSaving(false); }
  }

  async function handleCancel(id: number) {
    if (!confirm('이 스케줄을 취소하시겠습니까?')) return;
    await scheduleApi.cancel(id);
    await loadAll();
  }

  // 주간 뷰용
  const weekDays = useMemo(() => {
    const days: { date: string; label: string }[] = [];
    const total = getDaysInMonth(year, month);
    for (let d = 1; d <= total; d++) {
      const dt = new Date(year, month - 1, d);
      const w = Math.ceil(d / 7);
      if (w === week) {
        const dateStr = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        days.push({ date: dateStr, label: `${d}일(${DAY_KO[dt.getDay()]})` });
      }
    }
    return days;
  }, [year, month, week]);

  const maxWeek = Math.ceil(getDaysInMonth(year, month) / 7);

  const filtered = useMemo(() => {
    return schedules.filter((s) => {
      if (filter === 'ALL') return true;
      if (filter === 'REGULAR') return s.employee_type === 'REGULAR';
      if (filter === 'PART_TIMER') return s.employee_type === 'PART_TIMER';
      return s.store_name === filter;
    });
  }, [schedules, filter]);

  const filteredWeek = useMemo(() =>
    filtered.filter(s => weekDays.some(d => d.date === s.work_date)),
    [filtered, weekDays]);

  const byDate = useMemo(() => {
    const map: Record<string, ScheduleEntry[]> = {};
    for (const d of weekDays) map[d.date] = [];
    for (const s of filteredWeek) {
      if (map[s.work_date]) map[s.work_date].push(s);
    }
    for (const d of weekDays) {
      map[d.date].sort((a, b) => a.start_time.localeCompare(b.start_time));
    }
    return map;
  }, [filteredWeek, weekDays]);

  // 월간 뷰용
  const calGrid = useMemo(() => buildCalendarGrid(year, month), [year, month]);

  const byDateAll = useMemo(() => {
    const map: Record<string, ScheduleEntry[]> = {};
    for (const s of filtered) {
      if (!map[s.work_date]) map[s.work_date] = [];
      map[s.work_date].push(s);
    }
    for (const dt in map) {
      map[dt].sort((a, b) => a.start_time.localeCompare(b.start_time));
    }
    return map;
  }, [filtered]);

  function toDateStr(day: number) {
    return `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  }

  const today = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  const hardIssues = issues.filter((i) => i.type === 'HARD');
  const calDetailSchedules = calDetailDate ? (byDateAll[calDetailDate] || []) : [];

  return (
    <div>
      {/* 헤더 */}
      <div className="page-header sch-header">
        <div>
          <h2 className="page-title">스케줄</h2>
          <p className="page-subtitle">{year}년 {month}월 · 총 {schedules.length}건</p>
        </div>
        <div className="sch-header-actions">
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="emp-month-select">
            {[year-1, year, year+1].map((y) => <option key={y} value={y}>{y}년</option>)}
          </select>
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))} className="emp-month-select">
            {Array.from({length:12},(_,i)=>i+1).map((m) => <option key={m} value={m}>{m}월</option>)}
          </select>
          <button className="btn btn--secondary" onClick={() => { setAddDefaultDate(''); setEditTarget('new'); }}>
            + 스케줄 추가
          </button>
          <button className="btn btn--primary" onClick={handleGenerate} disabled={generating}>
            {generating ? '생성 중...' : '자동 스케줄 생성'}
          </button>
          <button className="btn btn--secondary" onClick={handleValidate} disabled={validating}>
            {validating ? '검증 중...' : '스케줄 검증'}
          </button>
          <button className="btn btn--secondary" onClick={handleDeduplicate}>
            중복 정리
          </button>
          <button
            className={`btn ${bulkDelConfirm ? 'btn--danger' : 'btn--secondary'}`}
            onClick={handleBulkDelete}
            onBlur={() => setBulkDelConfirm(false)}
          >
            {bulkDelConfirm ? '한번 더 클릭 시 삭제' : 'DRAFT 전체 삭제'}
          </button>
        </div>
      </div>

      {/* 생성 결과 */}
      {genResult && (
        <div className={`gen-result ${genResult.created === 0 ? 'gen-result--zero' : genResult.warnings.length > 0 ? 'gen-result--warn' : 'gen-result--ok'}`}>
          <strong>생성 완료: {genResult.created}개</strong>
          {genResult.created === 0 && (
            <div className="gen-zero-help">
              <p>스케줄이 생성되지 않았습니다. 아래 항목을 확인해주세요:</p>
              <ul>
                <li>📅 <strong>필요인원 설정 월 확인</strong> — 매장 관리 페이지의 "필요인원 설정 기준 월"을 <strong>{year}년 {month}월</strong>로 맞추고 다시 저장했는지 확인하세요 (기본값이 현재 달이라 다른 달로 저장됐을 수 있습니다)</li>
                <li>📋 <strong>매장 관리 → 필요인원</strong> — 매장별 시간대·인원수가 설정되어 있어야 파트타이머가 배정됩니다</li>
                <li>👔 <strong>직원 관리 → 근무패턴</strong> — 정규직은 요일별 근무패턴이 설정되어 있어야 배정됩니다</li>
                <li>👥 <strong>활성 직원 확인</strong> — 비활성화된 직원은 배정되지 않습니다</li>
              </ul>
            </div>
          )}
          {genResult.warnings.length > 0 && (
            <ul className="gen-warnings">
              {genResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* 검증 결과 */}
      {issues.length > 0 && (
        <div className="validation-panel">
          <h3 className="validation-title">⚠️ 검증 결과 — {hardIssues.length}개 위반 발견</h3>
          <ul className="validation-list">
            {issues.map((iss, i) => (
              <li key={i} className={`validation-item validation-item--${iss.type.toLowerCase()}`}>
                <span className="validation-badge">{iss.type}</span>
                {iss.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 뷰 전환 + 필터 */}
      <div className="sch-toolbar">
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10}}>
          <div className="emp-filters">
            {(['ALL','REGULAR','PART_TIMER'] as FilterType[]).map((f) => (
              <button key={f} className={`filter-btn ${filter===f?'filter-btn--active':''}`}
                onClick={() => setFilter(f)}>
                {f==='ALL'?'전체':f==='REGULAR'?'정규직':'파트타이머'}
              </button>
            ))}
            {stores.map((s) => (
              <button key={s.id} className={`filter-btn ${filter===s.name?'filter-btn--active':''}`}
                onClick={() => setFilter(s.name)}>
                {s.name}
              </button>
            ))}
          </div>
          <div className="view-toggle">
            <button className={`view-toggle-btn ${viewMode==='month'?'view-toggle-btn--active':''}`}
              onClick={() => setViewMode('month')}>📅 월간</button>
            <button className={`view-toggle-btn ${viewMode==='week'?'view-toggle-btn--active':''}`}
              onClick={() => setViewMode('week')}>📋 주간</button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="card"><p className="emp-empty">불러오는 중...</p></div>
      ) : schedules.length === 0 ? (
        <div className="card">
          <div className="coming-soon">
            <span className="coming-soon-icon">📅</span>
            <h3 className="coming-soon-title">스케줄이 없습니다</h3>
            <p className="coming-soon-desc">상단의 [자동 스케줄 생성] 버튼을 눌러 스케줄을 생성하세요.<br/>먼저 직원 관리에서 근무패턴을, 매장 관리에서 필요인원을 설정해야 합니다.</p>
          </div>
        </div>
      ) : viewMode === 'month' ? (
        /* ── 월간 캘린더 뷰 ── */
        <div className="cal-wrap">
          <div className="cal-save-bar">
            <button className="btn btn--secondary" onClick={handleSaveImage} disabled={saving}>
              {saving ? '저장 중...' : '📷 이미지 저장'}
            </button>
            <span className="cal-save-hint">저장된 이미지를 직원들에게 공유하세요</span>
          </div>
          <div ref={calRef} className="cal-capture">
            <div className="cal-capture-title">{year}년 {month}월 근무 스케줄</div>
            {stores.length > 0 && (
              <div className="cal-capture-stores">
                ({stores.map((s) => s.name).join(' · ')})
              </div>
            )}
          <div className="cal-grid">
            {/* 요일 헤더 */}
            {DAY_HEADER.map((d, i) => (
              <div key={d} className={`cal-header-cell ${i===5||i===6?'cal-header-cell--weekend':''}`}>{d}</div>
            ))}
            {/* 날짜 셀 */}
            {calGrid.map((row, ri) =>
              row.map((day, ci) => {
                if (!day) return <div key={`empty-${ri}-${ci}`} className="cal-cell cal-cell--empty" />;
                const dateStr = toDateStr(day);
                const daySchedules = byDateAll[dateStr] || [];
                const isToday = dateStr === today;
                const isSelected = calDetailDate === dateStr;
                const isWeekend = ci === 5 || ci === 6;
                return (
                  <div
                    key={dateStr}
                    className={`cal-cell ${isToday?'cal-cell--today':''} ${isSelected?'cal-cell--selected':''} ${isWeekend?'cal-cell--weekend':''}`}
                    onClick={() => setCalDetailDate(isSelected ? null : dateStr)}
                  >
                    <div className="cal-day-num">{day}</div>
                    <div className="cal-chips">
                      {daySchedules.map(s => (
                        <div key={s.id}
                          className={`cal-chip ${s.employee_type==='REGULAR'?'cal-chip--regular':'cal-chip--part'} ${s.status==='CONFIRMED'?'cal-chip--confirmed':''} ${s.status!=='LOCKED'?'cal-chip--clickable':''}`}
                          onClick={(e) => { if (s.status !== 'LOCKED') { e.stopPropagation(); setEditTarget(s); } }}
                          title={s.status !== 'LOCKED' ? '클릭하여 수정' : '잠금된 스케줄'}
                        >
                          <span className="cal-chip-name">{s.employee_name}</span>
                          <span className="cal-chip-sep">—</span>
                          <span className="cal-chip-time">{s.start_time.slice(0,5)}~{s.end_time.slice(0,5)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          </div>{/* cal-capture 끝 */}

          {/* 날짜 클릭 시 상세 패널 */}
          {calDetailDate && (
            <div className="cal-detail-panel">
              <div className="cal-detail-header">
                <strong>{calDetailDate.replace(/-/g, '.')} ({DAY_KO[new Date(calDetailDate).getDay()]})</strong>
                <span className="cal-detail-count">{calDetailSchedules.length}건</span>
                <button className="btn btn--primary btn--sm" style={{marginLeft:'auto',marginRight:8}}
                  onClick={() => { setAddDefaultDate(calDetailDate); setEditTarget('new'); }}>
                  + 추가
                </button>
                <button className="cal-detail-close" onClick={() => setCalDetailDate(null)}>✕</button>
              </div>
              {calDetailSchedules.length === 0 ? (
                <p className="emp-empty">이 날 스케줄이 없습니다.</p>
              ) : (
                <div className="cal-detail-list">
                  {calDetailSchedules.map(s => (
                    <div key={s.id} className={`sch-card ${s.employee_type==='REGULAR'?'sch-card--regular':'sch-card--part'} ${s.status==='CONFIRMED'?'sch-card--confirmed':''}`}>
                      <div className="sch-card-name">{s.employee_name}</div>
                      <div className="sch-card-time">{s.start_time}~{s.end_time}</div>
                      <div className="sch-card-store">{s.store_name}</div>
                      <div className="sch-card-actions">
                        <span className={`sch-status sch-status--${s.status.toLowerCase()}`}>
                          {s.status==='DRAFT'?'작성중':s.status==='CONFIRMED'?'확정':'잠금'}
                        </span>
                        {s.status !== 'LOCKED' && (
                          <>
                            <button className="sch-btn" onClick={() => setEditTarget(s)}>수정</button>
                            <button className="sch-btn sch-btn--del" onClick={() => handleCancel(s.id)}>취소</button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* ── 주간 뷰 ── */
        <>
          <div className="week-tabs">
            {Array.from({length: maxWeek}, (_, i) => i+1).map((w) => (
              <button key={w} className={`week-tab ${week===w?'week-tab--active':''}`}
                onClick={() => setWeek(w)}>{w}주차</button>
            ))}
          </div>
          <div className="sch-grid">
            {weekDays.map(({date: d, label}) => {
              const daySchedules = byDate[d] || [];
              return (
                <div key={d} className="sch-day-col">
                  <div className="sch-day-header">{label}</div>
                  <div className="sch-day-body">
                    {daySchedules.length === 0 && <p className="sch-empty-day">-</p>}
                    {daySchedules.map((s) => (
                      <div key={s.id}
                        className={`sch-card ${s.status==='LOCKED'?'sch-card--locked':s.status==='CONFIRMED'?'sch-card--confirmed':''} ${s.employee_type==='REGULAR'?'sch-card--regular':'sch-card--part'}`}>
                        <div className="sch-card-name">{s.employee_name}</div>
                        <div className="sch-card-time">{s.start_time}~{s.end_time}</div>
                        <div className="sch-card-store">{s.store_name}</div>
                        <div className="sch-card-actions">
                          <span className={`sch-status sch-status--${s.status.toLowerCase()}`}>
                            {s.status==='DRAFT'?'작성중':s.status==='CONFIRMED'?'확정':'잠금'}
                          </span>
                          {s.status !== 'LOCKED' && (
                            <>
                              <button className="sch-btn" onClick={() => setEditTarget(s)}>수정</button>
                              <button className="sch-btn sch-btn--del" onClick={() => handleCancel(s.id)}>취소</button>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {editTarget !== null && (
        <ScheduleEditModal
          schedule={editTarget === 'new' ? null : editTarget}
          defaultDate={addDefaultDate}
          stores={stores} employees={employees}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); loadAll(); }}
        />
      )}
    </div>
  );
}
