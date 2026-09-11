import { useState, useEffect } from 'react';
import { api } from '../services/api';
import './History.css';

interface HistoryEntry {
  id: number;
  schedule_id: number;
  employee_name: string;
  store_name: string;
  work_date: string;
  change_reason: string;
  changed_by: string;
  changed_at: string;
  before_data: Record<string, unknown>;
  after_data: Record<string, unknown>;
}

const REASON_LABELS: Record<string, string> = {
  MANUAL_EDIT: '수동 수정',
  STATUS_CHANGE: '상태 변경',
  EMPLOYEE_REQUEST: '직원 요청',
  STORE_REQUEST: '매장 요청',
  ERROR_CORRECTION: '오류 수정',
  OTHER: '기타',
};

export default function History() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => { load(); }, [year, month]);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get(`/history/${year}/${month}`);
      setEntries(r.data);
    } catch { setEntries([]); }
    finally { setLoading(false); }
  }

  function toggle(id: number) {
    setExpanded(expanded === id ? null : id);
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">변경 이력</h2>
          <p className="page-subtitle">스케줄 수정 · 상태 변경 기록</p>
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

      {loading ? <p className="emp-empty">불러오는 중...</p> : entries.length === 0 ? (
        <div className="card" style={{textAlign:'center',padding:'60px 20px',color:'#8b8fa8'}}>
          <p style={{fontSize:36,margin:'0 0 12px'}}>📋</p>
          <p style={{margin:0,fontSize:15}}>이 달의 변경 이력이 없습니다.</p>
        </div>
      ) : (
        <div className="card hist-table-wrap">
          <table className="emp-table">
            <thead>
              <tr>
                <th>일시</th><th>직원</th><th>매장</th><th>근무일</th>
                <th>변경 사유</th><th>수정자</th><th></th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <>
                  <tr key={e.id} className={expanded===e.id?'hist-row--selected':''}>
                    <td className="hist-date">{new Date(e.changed_at).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</td>
                    <td className="emp-name">{e.employee_name}</td>
                    <td>{e.store_name}</td>
                    <td>{e.work_date}</td>
                    <td>
                      <span className="hist-reason">{REASON_LABELS[e.change_reason] ?? e.change_reason}</span>
                    </td>
                    <td>{e.changed_by || '관리자'}</td>
                    <td>
                      <button className="btn btn--ghost btn--sm" onClick={()=>toggle(e.id)}>
                        {expanded===e.id?'닫기':'상세'}
                      </button>
                    </td>
                  </tr>
                  {expanded === e.id && (
                    <tr key={`${e.id}-detail`}>
                      <td colSpan={7} className="hist-detail-td">
                        <div className="hist-diff">
                          <div className="hist-diff-col hist-diff-col--before">
                            <p className="hist-diff-label">변경 전</p>
                            <pre className="hist-pre">{JSON.stringify(e.before_data, null, 2)}</pre>
                          </div>
                          <div className="hist-diff-col hist-diff-col--after">
                            <p className="hist-diff-label">변경 후</p>
                            <pre className="hist-pre">{JSON.stringify(e.after_data, null, 2)}</pre>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
