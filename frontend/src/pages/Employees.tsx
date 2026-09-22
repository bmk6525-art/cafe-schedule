import { useState, useEffect, useMemo } from 'react';
import type { Employee, Store } from '../types';
import { employeeApi, storeApi, availabilityApi } from '../services/api';
import { useMonth } from '../context/MonthContext';
import EmployeeModal from '../components/employees/EmployeeModal';
import WorkPatternModal from '../components/employees/WorkPatternModal';
import AvailabilityModal from '../components/employees/AvailabilityModal';
import './Employees.css';

type FilterType = 'ALL' | 'REGULAR' | 'PART_TIMER';

export default function Employees() {
  const { year: avYear, month: avMonth } = useMonth();

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState<FilterType>('ALL');
  const [showInactive, setShowInactive] = useState(false);

  // 직원 순서 (localStorage 영속)
  const [orderIds, setOrderIds] = useState<number[]>(() => {
    try {
      const s = localStorage.getItem('cafe_emp_order');
      return s ? JSON.parse(s) : [];
    } catch { return []; }
  });
  const [dragId, setDragId] = useState<number | null>(null);
  const [dragOverId, setDragOverId] = useState<number | null>(null);

  // 가용성 입력 현황 (employee_id → {available_count, unavailable_count})
  const [availStatusIds, setAvailStatusIds] = useState<number[]>([]);
  const [availDetails, setAvailDetails] = useState<Record<number, { available_count: number; unavailable_count: number }>>({});
  // 로컬 저장 (저장 버튼 클릭 시 즉시 반영, API 실패와 무관하게 배지 표시)
  const [localAvailMap, setLocalAvailMap] = useState<Record<number, { ac: number; uc: number }>>(() => {
    try {
      const raw = localStorage.getItem(`cafe_avail_${new Date().getFullYear()}_${new Date().getMonth() + 1}`);
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  });

  // 불가능시간 일괄 복사 상태
  const now = new Date();
  const [bulkCopyFromYear, setBulkCopyFromYear] = useState(now.getFullYear());
  const [bulkCopyFromMonth, setBulkCopyFromMonth] = useState(now.getMonth() + 1);
  const [bulkCopying, setBulkCopying] = useState(false);

  const [editTarget, setEditTarget] = useState<Employee | null | 'new'>(null);
  const [patternTarget, setPatternTarget] = useState<Employee | null>(null);
  const [avTarget, setAvTarget] = useState<Employee | null>(null);

  const [deactivateTarget, setDeactivateTarget] = useState<Employee | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [hardDeleteTarget, setHardDeleteTarget] = useState<Employee | null>(null);
  const [hardDeleting, setHardDeleting] = useState(false);

  useEffect(() => { loadAll(); }, [showInactive]);
  useEffect(() => {
    loadAvailStatus();
    try {
      const raw = localStorage.getItem(`cafe_avail_${avYear}_${avMonth}`);
      setLocalAvailMap(raw ? JSON.parse(raw) : {});
    } catch { setLocalAvailMap({}); }
  }, [avYear, avMonth]);

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

  async function loadAvailStatus() {
    try {
      const res = await availabilityApi.getStatus(avYear, avMonth);
      setAvailStatusIds(res.data.employee_ids || []);
      // 상세 카운트 맵 구성
      const detailMap: Record<number, { available_count: number; unavailable_count: number }> = {};
      for (const d of (res.data.details || [])) {
        detailMap[d.employee_id] = {
          available_count: d.available_count ?? 0,
          unavailable_count: d.unavailable_count ?? 0,
        };
      }
      setAvailDetails(detailMap);
    } catch {
      // API 실패 시 기존 상태 유지 (localAvailMap으로 배지 표시)
    }
  }

  function handleAvailSaved(empId: number, ac: number, uc: number) {
    const updated = { ...localAvailMap, [empId]: { ac, uc } };
    setLocalAvailMap(updated);
    try {
      localStorage.setItem(`cafe_avail_${avYear}_${avMonth}`, JSON.stringify(updated));
    } catch { /* ignore */ }
    // API 상태도 즉시 업데이트
    if (!availStatusIds.includes(empId)) {
      setAvailStatusIds((prev) => [...prev, empId]);
    }
    setAvailDetails((prev) => ({
      ...prev,
      [empId]: { available_count: ac, unavailable_count: uc },
    }));
  }

  function getStoreName(id?: number | null) {
    if (!id) return '-';
    return stores.find((s) => s.id === id)?.name ?? '-';
  }

  // 전체 직원 순서 적용
  const orderedEmployees = useMemo(() => {
    if (orderIds.length === 0) return employees;
    return [...employees].sort((a, b) => {
      const ai = orderIds.indexOf(a.id);
      const bi = orderIds.indexOf(b.id);
      if (ai === -1 && bi === -1) return 0;
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  }, [employees, orderIds]);

  const filtered = useMemo(() => {
    return orderedEmployees.filter((e) => {
      const matchType = filterType === 'ALL' || e.employee_type === filterType;
      const matchSearch = e.name.includes(search.trim());
      return matchType && matchSearch;
    });
  }, [orderedEmployees, filterType, search]);

  // 드래그 핸들러
  function handleDragStart(e: React.DragEvent, id: number) {
    setDragId(id);
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDragOver(e: React.DragEvent, id: number) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverId !== id) setDragOverId(id);
  }

  function handleDrop(targetId: number) {
    if (dragId === null || dragId === targetId) {
      setDragId(null); setDragOverId(null); return;
    }
    const allIds = orderedEmployees.map((e) => e.id);
    const fromIdx = allIds.indexOf(dragId);
    const toIdx = allIds.indexOf(targetId);
    if (fromIdx === -1 || toIdx === -1) {
      setDragId(null); setDragOverId(null); return;
    }
    const newIds = [...allIds];
    newIds.splice(fromIdx, 1);
    newIds.splice(toIdx, 0, dragId);
    setOrderIds(newIds);
    localStorage.setItem('cafe_emp_order', JSON.stringify(newIds));
    setDragId(null); setDragOverId(null);
  }

  function handleDragEnd() {
    setDragId(null); setDragOverId(null);
  }

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

  async function handleBulkCopyAv() {
    if (!confirm(`${bulkCopyFromYear}년 ${bulkCopyFromMonth}월 불가능시간 설정을 ${avYear}년 ${avMonth}월로 전체 복사합니다.\n기존 ${avYear}년 ${avMonth}월 데이터는 덮어씁니다. 계속하시겠습니까?`)) return;
    setBulkCopying(true);
    try {
      const res = await availabilityApi.bulkCopy(bulkCopyFromYear, bulkCopyFromMonth, avYear, avMonth);
      alert(res.data.message);
      await loadAvailStatus();
    } catch (e: any) {
      alert(`복사 오류: ${e.message}`);
    } finally {
      setBulkCopying(false);
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

      {/* 기준 월 표시 + 불가능시간 일괄 복사 */}
      <div className="emp-month-bar">
        <span className="emp-month-label">불가능시간 기준 월:</span>
        <span className="emp-month-cur">{avYear}년 {avMonth}월</span>
        <span className="emp-month-label" style={{marginLeft:16}}>다른 달에서 불러오기:</span>
        <select value={bulkCopyFromYear} onChange={(e) => setBulkCopyFromYear(Number(e.target.value))} className="emp-month-select">
          {[now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1].map((y) => (
            <option key={y} value={y}>{y}년</option>
          ))}
        </select>
        <select value={bulkCopyFromMonth} onChange={(e) => setBulkCopyFromMonth(Number(e.target.value))} className="emp-month-select">
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
            <option key={m} value={m}>{m}월</option>
          ))}
        </select>
        <button className="btn btn--secondary btn--sm" onClick={handleBulkCopyAv} disabled={bulkCopying}>
          {bulkCopying ? '복사 중...' : '전체 복사'}
        </button>
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
                <th className="emp-drag-th"></th>
                <th>이름</th>
                <th>구분</th>
                <th>불가능시간</th>
                <th>시급</th>
                <th>선호 매장</th>
                <th>입사일</th>
                <th>상태</th>
                <th>관리</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((emp) => (
                <tr
                  key={emp.id}
                  className={[
                    !emp.is_active ? 'emp-row--inactive' : '',
                    dragId === emp.id ? 'emp-row--dragging' : '',
                    dragOverId === emp.id && dragId !== emp.id ? 'emp-row--dragover' : '',
                  ].filter(Boolean).join(' ')}
                  draggable
                  onDragStart={(e) => handleDragStart(e, emp.id)}
                  onDragOver={(e) => handleDragOver(e, emp.id)}
                  onDrop={() => handleDrop(emp.id)}
                  onDragEnd={handleDragEnd}
                >
                  <td className="emp-drag-cell">☰</td>
                  <td className="emp-name">{emp.name}</td>
                  <td>
                    <span className={`type-badge ${emp.employee_type === 'REGULAR' ? 'type-badge--regular' : 'type-badge--part'}`}>
                      {emp.employee_type === 'REGULAR' ? '정규직' : '파트타이머'}
                    </span>
                  </td>
                  <td>
                    {emp.employee_type === 'PART_TIMER' && emp.is_active ? (() => {
                      // 로컬 저장 우선, 없으면 API 상태 사용
                      const localEntry = localAvailMap[emp.id];
                      const hasAny = localEntry != null || availStatusIds.includes(emp.id);
                      if (!hasAny) {
                        return <span className="av-badge av-badge--missing">미입력</span>;
                      }
                      const detail = availDetails[emp.id];
                      const ac = localEntry?.ac ?? detail?.available_count ?? 0;
                      const uc = localEntry?.uc ?? detail?.unavailable_count ?? 0;
                      const parts: string[] = [];
                      if (ac > 0) parts.push(`가능 ${ac}`);
                      if (uc > 0) parts.push(`불가 ${uc}`);
                      const label = parts.length > 0 ? `입력됨 (${parts.join(' / ')})` : '입력됨';
                      return (
                        <span
                          className="av-badge av-badge--ok av-badge--detail"
                          title={`가능 ${ac}개 / 불가능 ${uc}개`}
                        >
                          {label}
                        </span>
                      );
                    })() : (
                      <span className="emp-dash">—</span>
                    )}
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
          stores={stores}
          onSaved={(ac, uc) => handleAvailSaved(avTarget.id, ac, uc)}
          onClose={() => { setAvTarget(null); loadAvailStatus(); }}
        />
      )}

      {/* 비활성화 확인 */}
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

      {/* 영구 삭제 확인 */}
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
