import { useState, useEffect } from 'react';
import type { Store } from '../../types';
import { storeApi } from '../../services/api';
import '../../components/employees/EmployeeModal.css';

interface Props {
  store: Store | null;  // null이면 추가 모드
  onClose: () => void;
  onSaved: () => void;
}

const EMPTY_FORM = {
  name: '',
  open_time: '09:00',
  close_time: '23:00',
  memo: '',
};

export default function StoreModal({ store, onClose, onSaved }: Props) {
  const isEdit = store !== null;
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (store) {
      setForm({
        name: store.name,
        open_time: store.open_time,
        close_time: store.close_time,
        memo: store.memo ?? '',
      });
    }
  }, [store]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setError('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) { setError('매장 이름을 입력해 주세요.'); return; }
    if (!form.open_time)   { setError('운영 시작 시간을 입력해 주세요.'); return; }
    if (!form.close_time)  { setError('운영 종료 시간을 입력해 주세요.'); return; }
    if (form.open_time >= form.close_time) {
      setError('종료 시간은 시작 시간보다 늦어야 합니다.');
      return;
    }

    setSaving(true);
    setError('');
    try {
      const payload = {
        name: form.name.trim(),
        open_time: form.open_time,
        close_time: form.close_time,
        memo: form.memo || null,
      };
      if (isEdit) {
        await storeApi.update(store!.id, payload);
      } else {
        await storeApi.create(payload);
      }
      onSaved();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{isEdit ? '매장 정보 수정' : '매장 추가'}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          <div className="form-section">
            <div className="form-group form-group--required" style={{ marginBottom: 12 }}>
              <label>매장 이름</label>
              <input
                name="name"
                value={form.name}
                onChange={handleChange}
                placeholder="예: 1호점, 강남점"
              />
            </div>

            <div className="form-row">
              <div className="form-group form-group--required">
                <label>운영 시작 시간</label>
                <input
                  type="time"
                  name="open_time"
                  value={form.open_time}
                  onChange={handleChange}
                />
              </div>
              <div className="form-group form-group--required">
                <label>운영 종료 시간</label>
                <input
                  type="time"
                  name="close_time"
                  value={form.close_time}
                  onChange={handleChange}
                />
              </div>
            </div>

            <div className="form-group">
              <label>메모</label>
              <textarea
                name="memo"
                value={form.memo}
                onChange={handleChange}
                rows={2}
                placeholder="메모를 입력하세요"
              />
            </div>
          </div>

          {error && <p className="form-error">{error}</p>}

          <div className="modal-footer">
            <button type="button" className="btn btn--secondary" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn--primary" disabled={saving}>
              {saving ? '저장 중...' : isEdit ? '수정 완료' : '매장 추가'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
