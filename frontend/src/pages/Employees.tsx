import { useState, useEffect, useMemo } from 'react';
import type { Employee, Store } from '../types';
import { employeeApi, storeApi } from '../services/api';
import EmployeeModal from '../components/employees/EmployeeModal';
import WorkPatternModal from '../components/employees/WorkPatternModal';
import AvailabilityModal from '../components/employees/AvailabilityModal';
import './Employees.css';

type FilterType = 'ALL' | 'REGULAR' | 'PART_TIMER';

export default function Employees() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState<FilterType>('ALL');
  const [showInactive, setShowInactive] = useState(false);

  // 모달 상태
  const now = new Date();
  const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const [avYear, setAvYear] = useState(nextMonth.getFullYear());
  const [avMonth, setAvMonth] = useState(nextMonth.getMonth() + 1);

  const [editTarget, setEditTarget] = useState<Employee | null | 'new'>(null);
  const [patternTarget, setPatternTarget] = useState<Employee | null>(null);
  const [avTarget, setAvTarget] = useState<Employee | null>(null);

  // 비활성화 / 활성화 확인 상태
  const [deactivateTarget, setDeactivateTarget] = useState<Employee | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [hardDeleteTarget, setHardDeleteTarget] = useState<Employee | null>(null);
  const [hardDeleting, setHardDeleting] = useState(false);

  useEffect(() => {
    loadAll();
  }, [showInactive]);

  async function loadAll() {
    setLoading(true);
    try {
      const [empRes, storeRes] = await Promise.all([
        employeeApi.getAll({ includeInactive: showInactive }),
        storeApi.getAll(),
      ]);
      setEmployees(empRes.data);
      setStores(storeRes.data);
    } finally {
      setLoading(false);
    }
  }

  function getStoreName(id?: number | null) {
    if (!id) return '-';
    return stores.find((s) => s.id === id)?.name ?? '-';
  }

  const filtered = useMemo(() => {
    return employees.filter((e) => {
      const matchType = filterType === 'ALL' || e.employee_type === filterType;
      const matchSearch = e.name.includes(search.trim());
      return matchType && matchSearch;
    });
  }, [employees, filterType, search]);

  async function handleDeactivate() {
    if (!deactivateTarget) return;
    setDeactivating(true);
    try {
      await employeeApi.deactivate(deactivateTarget.id);
      setDeactivateTarget(null);
      await loadAll();
    } finally {
      setDeactivating(false);
    }
  }

  async function handleActivate(emp: Employee) {
    if (!confirm(`'${emp.name}'을(를) 다시 활성화하시겠습니까?`)) return;
    setActivating(true);
    try {
      await employeeApi.activate(emp.id);
      await loadAll();
    } finally {
      setActivating(false);
    }
  }

  async function handleHardDelete() {
    if (!hardDeleteTarget) return;
    setHardDeleting(true);
    try {
      await employeeApi.hardDelete(hardDeleteTarget.id);
      setHardDeleteTarget(null);
      await loadAll();
    } finally {
      setHardDeleting(false);
    }
  }

  const regulars = employees.filter((e) => e.employee_type === 'REGULAR' && e.is_active).length;
  const parts = employees.filter((e) => e.employee_type === 'PART_TIMER' && e.is_active).length;

  return (
    <div>
      {/* 헤더 */}
      <div className="page-header emp-header">
        <div>
          <h2 className="page-title">직원 관리</h2>
          <p className="page-subtitle">
            정규직 <strong>{regulars}명</strong> &nbsp;·&nbsp; 파트타이머 <strong>{parts}명</strong>
          </p>
        </div>
        <button className="btn btn--primary" onClick={() => setEditTarget('new')}>
          + 직원 추가
        </button>
      </div>

      {/* 월 선택 (파트타이머 불가능시간용) */}
      <div className="emp-month-bar">
        <span className="emp-month-label">불가능시간 설정 기준 월:</span>
        <select value={avYear} onChange={(e) => setAvYear(Number(e.target.value))} className="emp-month-select">
          {[now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1].map((y) => (
            <option key={y} value={y}>{y}년</option>
          ))}
        </select>
        <select value={avMonth} onChange={(e) => setAvMonth(Number(e.target.value))} className="emp-month-select">
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
            <option key={m} value={m}>{m}월</option>
          ))}
        </select>
      </div>

      {/* 검색 및 필터 */}
      <div className="emp-toolbar">
        <input
          className="emp-search"
          placeholder="이름으로 검색..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="emp-filters">
          {(['ALL', 'REGULAR', 'PART_TIMER'] as FilterType[]).map((t) => (
            <button
              key={t}
              className={`filter-btn ${filterType === t ? 'filter-btn--active' : ''}`}
              onClick={() => setFilterType(t)}
            >
              {t === 'ALL' ? '전체' : t === 'REGULAR' ? '정규직' : '파트타이머'}
            </button>
          ))}
        </div>
        <label className="inactive-toggle">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          비활성 포함
        </label>
      </div>

      {/* 테이블 */}
      <div className="card emp-table-wrap">
        {loading ? (
          <p className="emp-empty">불러오는 중...</p>
        ) : filtered.length === 0 ? (
          <p className="emp-empty">
            {employees.length === 0
              ? '등록된 직원이 없습니다. 대시보드에서 테스트 데이터를 먼저 생성해 보세요.'
              : '검색 결과가 없습니다.'}
          </p>
        ) : (
          <table className="emp-table">
            <thead>
              <tr>
                <th>이름</th>
                <th>구분</th>
                <th>시급</th>
                <th>선호 매장</th>
                <th>입사일</th>
                <th>상태</th>
                <th>관리</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((emp) => (
                <tr key={emp.id} className={!emp.is_active ? 'emp-row--inactive' : ''}>
                  <td className="emp-name">{emp.name}</td>
                  <td>
                    <span className={`type-badge ${emp.employee_type === 'REGULAR' ? 'type-badge--regular' : 'type-badge--part'}`}>
                      {emp.employee_type === 'REGULAR' ? '정규직' : '파트타이머'}
                    </span>
                  </td>
                  <td className="emp-wage">{emp.hourly_wage.toLocaleString()}원</td>
                  <td>{getStoreName(emp.preferred_store_id)}</td>
                  <td>{emp.hire_date ?? '-'}</td>
                  <td>
                    <span className={`status-badge ${emp.is_active ? 'status-badge--active' : 'status-badge--inactive'}`}>
                      {emp.is_active ? '활성' : '비활성'}
                    </span>
                  </td>
                  <td className="emp-actions">
                    <button className="btn btn--ghost btn--sm" onClick={() => setEditTarget(emp)}>
                      수정
                    </button>
                    {emp.employee_type === 'REGULAR' && emp.is_active && (
                      <button className="btn btn--ghost btn--sm" onClick={() => setPatternTarget(emp)}>
                        근무패턴
                      </button>
                    )}
                    {emp.employee_type === 'PART_TIMER' && emp.is_active && (
                      <button className="btn btn--ghost btn--sm" onClick={() => setAvTarget(emp)}>
                        불가능시간
                      </button>
                    )}
                    {emp.is_active ? (
                      <button className="btn btn--danger btn--sm" onClick={() => setDeactivateTarget(emp)}>
                        비활성화
                      </button>
                    ) : (
                      <>
                        <button className="btn btn--success btn--sm" onClick={() => handleActivate(emp)} disabled={activating}>
                          활성화
                        </button>
                        <button className="btn btn--delete btn--sm" onClick={() => setHardDeleteTarget(emp)}>
                          영구삭제
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 직원 추가/수정 모달 */}
      {editTarget !== null && (
        <EmployeeModal
          employee={editTarget === 'new' ? null : editTarget}
          stores={stores}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); loadAll(); }}
        />
      )}

      {/* 근무패턴 모달 */}
      {patternTarget && (
        <WorkPatternModal
          employee={patternTarget}
          stores={stores}
          onClose={() => setPatternTarget(null)}
        />
      )}

      {/* 불가능시간 모달 */}
      {avTarget && (
        <AvailabilityModal
          employee={avTarget}
          year={avYear}
          month={avMonth}
          onClose={() => setAvTarget(null)}
        />
      )}

      {/* 비활성화 확인 다이얼로그 */}
      {deactivateTarget && (
        <div className="modal-backdrop" onClick={() => setDeactivateTarget(null)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 className="confirm-title">직원 비활성화</h3>
            <p className="confirm-desc">
              <strong>{deactivateTarget.name}</strong>을(를) 비활성화하시겠습니까?<br />
              비활성화된 직원은 스케줄에서 제외되지만 기존 데이터는 보존됩니다.
            </p>
            <div className="confirm-actions">
              <button className="btn btn--secondary" onClick={() => setDeactivateTarget(null)}>취소</button>
              <button className="btn btn--danger" onClick={handleDeactivate} disabled={deactivating}>
                {deactivating ? '처리 중...' : '비활성화'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 영구 삭제 확인 다이얼로그 */}
      {hardDeleteTarget && (
        <div className="modal-backdrop" onClick={() => setHardDeleteTarget(null)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 className="confirm-title" style={{color:'#c0392b'}}>⚠️ 직원 영구 삭제</h3>
            <p className="confirm-desc">
              <strong>{hardDeleteTarget.name}</strong>의 모든 데이터를 영구적으로 삭제합니다.<br />
              스케줄, 급여, 근무이력이 모두 삭제되며 <strong>복구할 수 없습니다.</strong>
            </p>
            <div className="confirm-actions">
              <button className="btn btn--secondary" onClick={() => setHardDeleteTarget(null)}>취소</button>
              <button className="btn btn--delete" onClick={handleHardDelete} disabled={hardDeleting}>
                {hardDeleting ? '삭제 중...' : '영구 삭제'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
