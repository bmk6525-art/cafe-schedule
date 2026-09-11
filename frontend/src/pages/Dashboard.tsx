import { useEffect, useState } from 'react';
import { employeeApi, storeApi, seedApi, api } from '../services/api';
import type { Employee, Store } from '../types';
import './Dashboard.css';

interface DashStats {
  total_schedules: number;
  total_hours: number;
  total_labor_cost: number;
  holiday_risk_count: number;
  understaffed_slots: number;
}

export default function Dashboard() {
  const now = new Date();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [stats, setStats] = useState<DashStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState('');

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const y = now.getFullYear(); const m = now.getMonth() + 1;
      const [empRes, storeRes, statsRes] = await Promise.all([
        employeeApi.getAll(),
        storeApi.getAll(),
        api.get(`/dashboard/stats?year=${y}&month=${m}`),
      ]);
      setEmployees(empRes.data);
      setStores(storeRes.data);
      setStats(statsRes.data);
    } catch { /* 서버 미연결 시 무시 */ }
    finally { setLoading(false); }
  }

  async function handleSeed() {
    setSeeding(true); setSeedMessage('');
    try {
      await seedApi.run();
      setSeedMessage('테스트 데이터가 성공적으로 생성되었습니다.');
      await loadData();
    } catch (err: any) {
      setSeedMessage(`오류: ${err.message}`);
    } finally { setSeeding(false); }
  }

  const regulars = employees.filter((e) => e.employee_type === 'REGULAR');
  const partTimers = employees.filter((e) => e.employee_type === 'PART_TIMER');
  const monthLabel = `${now.getFullYear()}년 ${now.getMonth()+1}월`;

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">대시보드</h2>
          <p className="page-subtitle">{monthLabel} 현황 요약</p>
        </div>
      </div>

      {/* 인원 현황 */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">🏪</div>
          <div className="stat-info">
            <p className="stat-label">운영 매장</p>
            <p className="stat-value">{loading ? '-' : stores.length}개</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">👔</div>
          <div className="stat-info">
            <p className="stat-label">정규 직원</p>
            <p className="stat-value">{loading ? '-' : regulars.length}명</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">🕐</div>
          <div className="stat-info">
            <p className="stat-label">파트타이머</p>
            <p className="stat-value">{loading ? '-' : partTimers.length}명</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📅</div>
          <div className="stat-info">
            <p className="stat-label">이번 달 스케줄</p>
            <p className="stat-value">{loading ? '-' : (stats?.total_schedules ?? 0)}건</p>
          </div>
        </div>
      </div>

      {/* 이번 달 통계 */}
      {stats && (
        <div className="stats-grid" style={{marginTop:0}}>
          <div className="stat-card stat-card--highlight">
            <div className="stat-icon">💰</div>
            <div className="stat-info">
              <p className="stat-label">예상 인건비 (주휴 포함)</p>
              <p className="stat-value">{stats.total_labor_cost.toLocaleString()}원</p>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">⏱️</div>
            <div className="stat-info">
              <p className="stat-label">파트 총 근무시간</p>
              <p className="stat-value">{stats.total_hours}시간</p>
            </div>
          </div>
          <div className={`stat-card ${stats.holiday_risk_count > 0 ? 'stat-card--warn' : ''}`}>
            <div className="stat-icon">⚠️</div>
            <div className="stat-info">
              <p className="stat-label">주휴수당 발생 인원</p>
              <p className="stat-value">{stats.holiday_risk_count}명</p>
            </div>
          </div>
          <div className={`stat-card ${stats.understaffed_slots > 0 ? 'stat-card--warn' : ''}`}>
            <div className="stat-icon">👥</div>
            <div className="stat-info">
              <p className="stat-label">인원 부족 슬롯</p>
              <p className="stat-value">{stats.understaffed_slots}건</p>
            </div>
          </div>
        </div>
      )}

      {/* 매장 정보 */}
      {stores.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3 className="card-title">운영 매장</h3>
          <div className="store-list">
            {stores.map((store) => (
              <div key={store.id} className="store-item">
                <span className="store-name">{store.name}</span>
                <span className="store-hours">{store.open_time} ~ {store.close_time}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 개발용 Seed 버튼 */}
      <div className="card dev-section">
        <div className="dev-section-header">
          <span className="badge badge--phase">개발용</span>
          <h3 className="card-title" style={{ margin: 0 }}>테스트 데이터 초기화</h3>
        </div>
        <p className="dev-desc">
          매장 3개(1~3호점)와 직원 8명(정규직 3명 + 파트타이머 5명)의 테스트 데이터를 생성합니다.
        </p>
        <button className="btn btn--primary" onClick={handleSeed} disabled={seeding}>
          {seeding ? '생성 중...' : '테스트 데이터 생성'}
        </button>
        {seedMessage && (
          <p className={`seed-message ${seedMessage.startsWith('오류') ? 'seed-message--error' : 'seed-message--success'}`}>
            {seedMessage}
          </p>
        )}
      </div>

      {/* 개발 로드맵 */}
      <div className="card phase-roadmap">
        <h3 className="card-title">개발 로드맵</h3>
        <div className="phase-list">
          {[
            { phase: 1,  name: '프로젝트 기본 구조 + DB', done: true },
            { phase: 2,  name: '직원 관리', done: true },
            { phase: 3,  name: '매장 관리', done: true },
            { phase: 4,  name: '파트타이머 가능/불가능 시간 관리', done: true },
            { phase: 5,  name: '매장별 시간대 필요인원 관리', done: true },
            { phase: 6,  name: '스케줄 자동 생성 엔진', done: true },
            { phase: 7,  name: '스케줄 조회 및 수동 수정', done: true },
            { phase: 8,  name: '스케줄 검증', done: true },
            { phase: 9,  name: '실제 근무시간 관리', done: true },
            { phase: 10, name: '급여 및 주휴수당 계산', done: true },
            { phase: 11, name: '월별 저장/복사/마감', done: true },
            { phase: 12, name: '변경 이력', done: true },
            { phase: 13, name: 'Claude AI 연동 (데모)', done: true },
            { phase: 14, name: '대시보드 및 통계', done: true },
          ].map((item) => (
            <div key={item.phase} className={`phase-item ${item.done ? 'phase-item--done' : ''}`}>
              <span className="phase-number">PHASE {item.phase}</span>
              <span className="phase-name">{item.name}</span>
              <span className="phase-status">{item.done ? '✅ 완료' : '⏳ 예정'}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
