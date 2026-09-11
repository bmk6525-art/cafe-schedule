import { useState, useEffect } from 'react';
import { api } from '../services/api';
import './MonthlyManage.css';

interface MonthStatus {
  year: number; month: number;
  is_finalized: boolean; finalized_at: string | null;
  schedule_count: number; confirmed_count: number;
}

export default function MonthlyManage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [status, setStatus] = useState<MonthStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [copyFrom, setCopyFrom] = useState<{year:number;month:number}>({year:now.getFullYear(), month:now.getMonth()===0?12:now.getMonth()});
  const [msg, setMsg] = useState<{type:'ok'|'err';text:string}|null>(null);

  useEffect(() => { loadStatus(); }, [year, month]);

  async function loadStatus() {
    setLoading(true);
    setMsg(null);
    try {
      const r = await api.get(`/monthly/${year}/${month}/status`);
      setStatus(r.data);
    } catch {
      setStatus(null);
    } finally { setLoading(false); }
  }

  function showMsg(type:'ok'|'err', text:string) {
    setMsg({type, text});
    setTimeout(() => setMsg(null), 4000);
  }

  async function finalize() {
    if (!confirm(`${year}년 ${month}월을 확정합니다. 확정 후에는 스케줄을 수정할 수 없습니다. 계속할까요?`)) return;
    try {
      await api.post(`/monthly/${year}/${month}/finalize`);
      showMsg('ok', `${year}년 ${month}월이 확정되었습니다.`);
      loadStatus();
    } catch (e: any) { showMsg('err', e.response?.data?.detail || '오류가 발생했습니다.'); }
  }

  async function copySettings() {
    try {
      await api.post(`/monthly/${year}/${month}/copy-settings`, {
        from_year: copyFrom.year, from_month: copyFrom.month,
      });
      showMsg('ok', `${copyFrom.year}년 ${copyFrom.month}월 설정을 복사했습니다.`);
    } catch (e: any) { showMsg('err', e.response?.data?.detail || '복사 실패'); }
  }

  const prevMonth = month === 1 ? 12 : month - 1;
  const prevYear  = month === 1 ? year - 1 : year;

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">월별 관리</h2>
          <p className="page-subtitle">월 확정 · 설정 복사 · 데이터 스냅샷</p>
        </div>
        <div style={{display:'flex',gap:8}}>
          <select value={year} onChange={e=>setYear(Number(e.target.value))} className="emp-month-select">
            {[year-1,year,year+1].map(y=><option key={y} value={y}>{y}년</option>)}
          </select>
          <select value={month} onChange={e=>setMonth(Number(e.target.value))} className="emp-month-select">
            {Array.from({length:12},(_,i)=>i+1).map(m=><option key={m} value={m}>{m}월</option>)}
          </select>
        </div>
      </div>

      {msg && <div className={`mm-msg mm-msg--${msg.type}`}>{msg.text}</div>}

      {loading ? <p className="emp-empty">불러오는 중...</p> : (
        <div className="mm-grid">
          {/* 월 상태 */}
          <div className="card mm-card">
            <h3 className="card-title">월 상태</h3>
            {status ? (
              <>
                <div className="mm-stat-row">
                  <span>전체 스케줄</span>
                  <strong>{status.schedule_count}건</strong>
                </div>
                <div className="mm-stat-row">
                  <span>확정 스케줄</span>
                  <strong>{status.confirmed_count}건</strong>
                </div>
                <div className="mm-stat-row">
                  <span>월 확정 여부</span>
                  {status.is_finalized
                    ? <span className="mm-badge mm-badge--done">확정완료</span>
                    : <span className="mm-badge mm-badge--draft">미확정</span>}
                </div>
                {status.finalized_at && (
                  <p className="mm-finalized-at">확정일시: {new Date(status.finalized_at).toLocaleString('ko-KR')}</p>
                )}
                {!status.is_finalized && (
                  <button className="btn btn--primary mm-action-btn" onClick={finalize}>
                    {year}년 {month}월 확정하기
                  </button>
                )}
              </>
            ) : (
              <p className="emp-empty">스케줄 데이터가 없습니다.</p>
            )}
          </div>

          {/* 설정 복사 */}
          <div className="card mm-card">
            <h3 className="card-title">설정 복사</h3>
            <p className="mm-desc">다른 월의 필요 인원·근무 패턴 설정을 현재 월로 복사합니다.</p>
            <div className="mm-copy-row">
              <select
                value={`${copyFrom.year}-${copyFrom.month}`}
                onChange={e => {
                  const [y,m] = e.target.value.split('-').map(Number);
                  setCopyFrom({year:y, month:m});
                }}
                className="emp-month-select"
              >
                {[-2,-1,0].map(d=>{
                  const t=new Date(year,month-1+d,1);
                  return <option key={d} value={`${t.getFullYear()}-${t.getMonth()+1}`}>
                    {t.getFullYear()}년 {t.getMonth()+1}월
                  </option>;
                })}
              </select>
              <span className="mm-arrow">→</span>
              <span className="mm-target">{year}년 {month}월</span>
            </div>
            <button className="btn btn--secondary mm-action-btn" onClick={copySettings}>설정 복사</button>
          </div>

          {/* 빠른 이동 */}
          <div className="card mm-card">
            <h3 className="card-title">빠른 이동</h3>
            <div className="mm-nav-btns">
              <button className="btn btn--secondary" onClick={()=>{ setMonth(prevMonth); setYear(prevYear); }}>
                ← {prevYear}년 {prevMonth}월
              </button>
              <button className="btn btn--secondary" onClick={()=>{
                const nm = month===12?1:month+1;
                const ny = month===12?year+1:year;
                setMonth(nm); setYear(ny);
              }}>
                {month===12?year+1:year}년 {month===12?1:month+1}월 →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
