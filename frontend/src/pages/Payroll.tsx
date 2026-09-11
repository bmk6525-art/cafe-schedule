import { useState, useEffect } from 'react';
import { api } from '../services/api';
import './Payroll.css';

interface DailyDetail {
  date: string; day_of_week: string;
  start_time: string; end_time: string;
  hours: number; store_name: string; is_actual: boolean;
}
interface WeekDetail {
  week_num: number; total_hours: number;
  is_holiday_pay_eligible: boolean; holiday_pay_amount: number;
}
interface PayrollRow {
  employee_id: number; employee_name: string; year: number; month: number;
  hourly_wage: number; total_hours: number; base_pay: number;
  holiday_pay: number; total_pay: number;
  daily_details: DailyDetail[]; weekly_details: WeekDetail[];
}
interface StoreSum { store_id: number; store_name: string; total_cost: number; }

export default function Payroll() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [rows, setRows] = useState<PayrollRow[]>([]);
  const [storeSums, setStoreSums] = useState<StoreSum[]>([]);
  const [selected, setSelected] = useState<PayrollRow | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadPayroll(); }, [year, month]);

  async function loadPayroll() {
    setLoading(true);
    setSelected(null);
    try {
      const [payRes, storeRes] = await Promise.all([
        api.get(`/payroll/${year}/${month}`),
        api.get(`/payroll/${year}/${month}/store-summary`),
      ]);
      setRows(payRes.data.filter((r: PayrollRow) => r.total_hours > 0));
      setStoreSums(storeRes.data);
    } finally { setLoading(false); }
  }

  const totalPay = rows.reduce((s, r) => s + r.total_pay, 0);
  const totalHoliday = rows.reduce((s, r) => s + r.holiday_pay, 0);

  // 주차별로 일별 상세를 그룹핑
  function groupByWeek(daily: DailyDetail[], weekly: WeekDetail[]) {
    const groups: { week: WeekDetail; days: DailyDetail[] }[] = [];
    for (const w of weekly) {
      const days = daily.filter(d => {
        const day = Number(d.date.split('-')[2]);
        return Math.ceil(day / 7) === w.week_num;
      });
      groups.push({ week: w, days });
    }
    return groups;
  }

  return (
    <div>
      <div className="page-header pay-header">
        <div>
          <h2 className="page-title">급여 관리</h2>
          <p className="page-subtitle">파트타이머 급여 및 주휴수당 · 실제 근무시간 기준</p>
        </div>
        <div style={{display:'flex', gap:8}}>
          <select value={year} onChange={e=>setYear(Number(e.target.value))} className="emp-month-select">
            {[year-1,year,year+1].map(y=><option key={y} value={y}>{y}년</option>)}
          </select>
          <select value={month} onChange={e=>setMonth(Number(e.target.value))} className="emp-month-select">
            {Array.from({length:12},(_,i)=>i+1).map(m=><option key={m} value={m}>{m}월</option>)}
          </select>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="pay-summary-grid">
        <div className="pay-summary-card">
          <p className="pay-sum-label">총 지급 예정액</p>
          <p className="pay-sum-value">{totalPay.toLocaleString()}원</p>
        </div>
        <div className="pay-summary-card">
          <p className="pay-sum-label">총 주휴수당</p>
          <p className="pay-sum-value">{totalHoliday.toLocaleString()}원</p>
        </div>
        <div className="pay-summary-card">
          <p className="pay-sum-label">대상 인원</p>
          <p className="pay-sum-value">{rows.length}명</p>
        </div>
      </div>

      <div className="pay-content">
        <div className="card pay-table-wrap">
          <h3 className="card-title">개인별 급여</h3>
          <p className="pay-notice">⚠️ 자동 계산 결과이며 실제 급여 지급 전 관리자 확인이 필요합니다.</p>

          {loading ? <p className="emp-empty">불러오는 중...</p> : rows.length === 0 ? (
            <p className="emp-empty">급여 데이터가 없습니다. 스케줄이 생성되어 있어야 합니다.</p>
          ) : (
            <table className="emp-table">
              <thead>
                <tr>
                  <th>이름</th><th>근무 매장</th><th>시급</th><th>근무시간</th>
                  <th>기본급</th><th>주휴수당</th><th>총 지급액</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  return (
                    <tr key={r.employee_id} className={selected?.employee_id===r.employee_id?'pay-row--selected':''}>
                      <td className="emp-name">{r.employee_name}</td>
                      <td className="pay-store-tags">
                        {[...new Set(r.daily_details.map(d => d.store_name))].map(s => (
                          <span key={s} className="pay-store-tag">{s}</span>
                        ))}
                      </td>
                      <td>{r.hourly_wage.toLocaleString()}원</td>
                      <td>{r.total_hours}시간</td>
                      <td>{r.base_pay.toLocaleString()}원</td>
                      <td>
                        {r.holiday_pay > 0
                          ? <span className="pay-holiday">{r.holiday_pay.toLocaleString()}원</span>
                          : '-'}
                      </td>
                      <td className="pay-total">{r.total_pay.toLocaleString()}원</td>
                      <td>
                        <button className="btn btn--ghost btn--sm"
                          onClick={() => setSelected(selected?.employee_id===r.employee_id ? null : r)}>
                          {selected?.employee_id===r.employee_id ? '닫기' : '상세'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {/* 일별 상세 */}
          {selected && (
            <div className="pay-detail">
              <div className="pay-detail-header">
                <span className="pay-detail-name">{selected.employee_name}</span>
                <span className="pay-detail-wage">시급 {selected.hourly_wage.toLocaleString()}원</span>
              </div>

              {groupByWeek(selected.daily_details, selected.weekly_details).map(({ week, days }) => (
                <div key={week.week_num} className="pay-week-section">
                  <div className={`pay-week-label-row ${week.is_holiday_pay_eligible ? 'pay-week-label-row--eligible' : ''}`}>
                    <span>{week.week_num}주차</span>
                    <span>{week.total_hours}시간</span>
                    {week.is_holiday_pay_eligible && (
                      <span className="pay-holiday-badge">주휴 +{week.holiday_pay_amount.toLocaleString()}원</span>
                    )}
                  </div>
                  {days.map((d, i) => {
                    const dayPay = Math.round(d.hours * selected.hourly_wage);
                    return (
                      <div key={i} className="pay-day-row">
                        <span className="pay-day-date">{d.date.slice(5).replace('-','/')}</span>
                        <span className="pay-day-dow">{d.day_of_week}요일</span>
                        <span className="pay-day-time">{d.start_time}~{d.end_time}</span>
                        <span className="pay-day-hours">({d.hours}시간)</span>
                        <span className="pay-day-store">{d.store_name}</span>
                        {d.is_actual && <span className="pay-day-actual">실근무</span>}
                        <span className="pay-day-pay">{dayPay.toLocaleString()}원</span>
                      </div>
                    );
                  })}
                </div>
              ))}

              <div className="pay-detail-total">
                <div className="pay-detail-total-row">
                  <span>총 근무시간</span>
                  <strong>{selected.total_hours}시간</strong>
                </div>
                <div className="pay-detail-total-row">
                  <span>기본급</span>
                  <strong>{selected.base_pay.toLocaleString()}원</strong>
                </div>
                {selected.holiday_pay > 0 && (
                  <div className="pay-detail-total-row">
                    <span>주휴수당</span>
                    <strong className="pay-holiday">+{selected.holiday_pay.toLocaleString()}원</strong>
                  </div>
                )}
                <div className="pay-detail-total-row pay-detail-total-row--final">
                  <span>월 급여 합계</span>
                  <strong>{selected.total_pay.toLocaleString()}원</strong>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 매장별 인건비 */}
        <div className="card pay-store-wrap">
          <h3 className="card-title">매장별 인건비</h3>
          {storeSums.map((s) => (
            <div key={s.store_id} className="pay-store-row">
              <span className="pay-store-name">{s.store_name}</span>
              <span className="pay-store-amount">{s.total_cost.toLocaleString()}원</span>
            </div>
          ))}
          <div className="pay-store-row pay-store-total">
            <span>합계</span>
            <span>{storeSums.reduce((a,s)=>a+s.total_cost,0).toLocaleString()}원</span>
          </div>
        </div>
      </div>
    </div>
  );
}
