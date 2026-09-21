import { useState, useEffect } from 'react';
import { useMonth } from '../context/MonthContext';
import type { Store } from '../types';
import { storeApi, requirementsApi } from '../services/api';
import StoreModal from '../components/stores/StoreModal';
import StaffRequirementsModal from '../components/stores/StaffRequirementsModal';
import './Stores.css';

export default function Stores() {
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);
  const now = new Date();
  const { year: reqYear, month: reqMonth } = useMonth();
  const [reqTarget, setReqTarget] = useState<Store | null>(null);

  // 필요인원 일괄 복사 상태
  const [bulkCopyFromYear, setBulkCopyFromYear] = useState(now.getFullYear());
  const [bulkCopyFromMonth, setBulkCopyFromMonth] = useState(now.getMonth() + 1);
  const [bulkCopying, setBulkCopying] = useState(false);

  const [editTarget, setEditTarget] = useState<Store | null | 'new'>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<Store | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [hardDeleteTarget, setHardDeleteTarget] = useState<Store | null>(null);
  const [hardDeleting, setHardDeleting] = useState(false);

  useEffect(() => {
    loadStores();
  }, [showInactive]);

  async function loadStores() {
    setLoading(true);
    try {
      const res = await storeApi.getAll(showInactive);
      setStores(res.data);
    } finally {
      setLoading(false);
    }
  }

  async function handleDeactivate() {
    if (!deactivateTarget) return;
    setDeactivating(true);
    try {
      await storeApi.deactivate(deactivateTarget.id);
      setDeactivateTarget(null);
      await loadStores();
    } finally {
      setDeactivating(false);
    }
  }

  async function handleActivate(store: Store) {
    if (!confirm(`'${store.name}'을(를) 다시 활성화하시겠습니까?`)) return;
    setActivating(true);
    try {
      await storeApi.activate(store.id);
      await loadStores();
    } finally {
      setActivating(false);
    }
  }

  async function handleHardDelete() {
    if (!hardDeleteTarget) return;
    setHardDeleting(true);
    try {
      await storeApi.hardDelete(hardDeleteTarget.id);
      setHardDeleteTarget(null);
      await loadStores();
    } finally {
      setHardDeleting(false);
    }
  }

  function calcOperatingHours(open: string, close: string) {
    const [oh, om] = open.split(':').map(Number);
    const [ch, cm] = close.split(':').map(Number);
    const mins = (ch * 60 + cm) - (oh * 60 + om);
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m === 0 ? `${h}시간` : `${h}시간 ${m}분`;
  }

  async function handleBulkCopyReq() {
    if (!confirm(`${bulkCopyFromYear}년 ${bulkCopyFromMonth}월 필요인원 설정을 ${reqYear}년 ${reqMonth}월로 전체 복사합니다.\n기존 ${reqYear}년 ${reqMonth}월 데이터는 덮어씁니다. 계속하시겠습니까?`)) return;
    setBulkCopying(true);
    try {
      const res = await requirementsApi.bulkCopy(bulkCopyFromYear, bulkCopyFromMonth, reqYear, reqMonth);
      alert(res.data.message);
    } catch (e: any) {
      alert(`복사 오류: ${e.message}`);
    } finally {
      setBulkCopying(false);
    }
  }

  const activeCount = stores.filter((s) => s.is_active).length;

  return (
    <div>
      {/* 헤더 */}
      <div className="page-header store-header">
        <div>
          <h2 className="page-title">매장 관리</h2>
          <p className="page-subtitle">현재 운영 중인 매장 <strong>{activeCount}개</strong></p>
        </div>
        <button className="btn btn--primary" onClick={() => setEditTarget('new')}>
          + 매장 추가
        </button>
      </div>

      {/* 월 선택 */}
      <div className="emp-month-bar">
        <span className="emp-month-label">필요인원 설정 기준 월:</span>
        <span style={{fontWeight:700, color:'#3a65e8', background:'#e8f0ff', padding:'3px 10px', borderRadius:'6px', fontSize:'13px'}}>
          {reqYear}년 {reqMonth}월
        </span>
        <span className="emp-month-label" style={{marginLeft:16}}>다른 달에서 불러오기:</span>
        <select value={bulkCopyFromYear} onChange={(e) => setBulkCopyFromYear(Number(e.target.value))} className="emp-month-select">
          {[now.getFullYear()-1, now.getFullYear(), now.getFullYear()+1].map((y) => (
            <option key={y} value={y}>{y}년</option>
          ))}
        </select>
        <select value={bulkCopyFromMonth} onChange={(e) => setBulkCopyFromMonth(Number(e.target.value))} className="emp-month-select">
          {Array.from({length:12},(_,i)=>i+1).map((m) => (
            <option key={m} value={m}>{m}월</option>
          ))}
        </select>
        <button className="btn btn--secondary btn--sm" onClick={handleBulkCopyReq} disabled={bulkCopying}>
          {bulkCopying ? '복사 중...' : '전체 복사'}
        </button>
      </div>

      {/* 비활성 포함 토글 */}
      <div className="store-toolbar">
        <label className="inactive-toggle">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          비활성 매장 포함
        </label>
      </div>

      {/* 매장 카드 목록 */}
      {loading ? (
        <p className="store-empty">불러오는 중...</p>
      ) : stores.length === 0 ? (
        <p className="store-empty">
          등록된 매장이 없습니다. 대시보드에서 테스트 데이터를 먼저 생성해 보세요.
        </p>
      ) : (
        <div className="store-grid">
          {stores.map((store) => (
            <div key={store.id} className={`store-card ${!store.is_active ? 'store-card--inactive' : ''}`}>
              <div className="store-card-header">
                <h3 className="store-card-name">{store.name}</h3>
                <span className={`status-badge ${store.is_active ? 'status-badge--active' : 'status-badge--inactive'}`}>
                  {store.is_active ? '운영 중' : '비활성'}
                </span>
              </div>

              <div className="store-card-hours">
                <span className="hours-label">운영시간</span>
                <span className="hours-value">
                  {store.open_time} ~ {store.close_time}
                </span>
                <span className="hours-duration">
                  ({calcOperatingHours(store.open_time, store.close_time)})
                </span>
              </div>

              {store.memo && (
                <p className="store-card-memo">{store.memo}</p>
              )}

              <div className="store-card-actions">
                <button className="btn btn--ghost btn--sm" onClick={() => setEditTarget(store)}>수정</button>
                {store.is_active && (
                  <button className="btn btn--ghost btn--sm" onClick={() => setReqTarget(store)}>
                    필요인원
                  </button>
                )}
                {store.is_active ? (
                  <button className="btn btn--danger btn--sm" onClick={() => setDeactivateTarget(store)}>
                    비활성화
                  </button>
                ) : (
                  <>
                    <button className="btn btn--success btn--sm" onClick={() => handleActivate(store)} disabled={activating}>
                      활성화
                    </button>
                    <button className="btn btn--delete btn--sm" onClick={() => setHardDeleteTarget(store)}>
                      영구삭제
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 필요인원 모달 */}
      {reqTarget && (
        <StaffRequirementsModal
          store={reqTarget} year={reqYear} month={reqMonth}
          allStores={stores.filter((s) => s.is_active)}
          onClose={() => setReqTarget(null)}
        />
      )}

      {/* 추가/수정 모달 */}
      {editTarget !== null && (
        <StoreModal
          store={editTarget === 'new' ? null : editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); loadStores(); }}
        />
      )}

      {/* 비활성화 확인 */}
      {deactivateTarget && (
        <div className="modal-backdrop" onClick={() => setDeactivateTarget(null)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 className="confirm-title">매장 비활성화</h3>
            <p className="confirm-desc">
              <strong>{deactivateTarget.name}</strong>을(를) 비활성화하시겠습니까?<br />
              비활성화된 매장은 스케줄 생성에서 제외되지만 기존 데이터는 보존됩니다.
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
            <h3 className="confirm-title" style={{color:'#c0392b'}}>⚠️ 매장 영구 삭제</h3>
            <p className="confirm-desc">
              <strong>{hardDeleteTarget.name}</strong>의 모든 데이터를 영구적으로 삭제합니다.<br />
              필요인원 설정, 스케줄이 모두 삭제되며 <strong>복구할 수 없습니다.</strong>
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
