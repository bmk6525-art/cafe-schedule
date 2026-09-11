import { useState, useEffect } from 'react';
import type { Employee, Store } from '../../types';
import { employeeApi } from '../../services/api';
import './EmployeeModal.css';

interface Props {
  employee: Employee | null;  // null이면 추가 모드, 값이 있으면 수정 모드
  stores: Store[];
  onClose: () => void;
  onSaved: () => void;
}

const EMPTY_FORM = {
  name: '',
  employee_type: 'PART_TIMER' as 'REGULAR' | 'PART_TIMER',
  hourly_wage: 10030,
  phone: '',
  hire_date: '',
  resign_date: '',
  preferred_store_id: '' as number | '',
  memo: '',
  monthly_target_hours: '' as number | '',
  monthly_min_hours: '' as number | '',
  monthly_max_hours: '' as number | '',
};

export default function EmployeeModal({ employee, stores, onClose, onSaved }: Props) {
  const isEdit = employee !== null;
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (employee) {
      setForm({
        name: employee.name,
        employee_type: employee.employee_type,
        hourly_wage: employee.hourly_wage,
        phone: employee.phone ?? '',
        hire_date: employee.hire_date ?? '',
        resign_date: employee.resign_date ?? '',
        preferred_store_id: employee.preferred_store_id ?? '',
        memo: employee.memo ?? '',
        monthly_target_hours: employee.monthly_target_hours ?? '',
        monthly_min_hours: employee.monthly_min_hours ?? '',
        monthly_max_hours: employee.monthly_max_hours ?? '',
      });
    }
  }, [employee]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setError('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) { setError('이름을 입력해 주세요.'); return; }
    if (!form.hourly_wage || Number(form.hourly_wage) < 0) { setError('시급을 올바르게 입력해 주세요.'); return; }

    setSaving(true);
    setError('');
    try {
      const payload = {
        name: form.name.trim(),
        employee_type: form.employee_type,
        hourly_wage: Number(form.hourly_wage),
        phone: form.phone || null,
        hire_date: form.hire_date || null,
        resign_date: form.resign_date || null,
        preferred_store_id: form.preferred_store_id !== '' ? Number(form.preferred_store_id) : null,
        memo: form.memo || null,
        monthly_target_hours: form.monthly_target_hours !== '' ? Number(form.monthly_target_hours) : null,
        monthly_min_hours: form.monthly_min_hours !== '' ? Number(form.monthly_min_hours) : null,
        monthly_max_hours: form.monthly_max_hours !== '' ? Number(form.monthly_max_hours) : null,
      };
      if (isEdit) {
        await employeeApi.update(employee!.id, payload);
      } else {
        await employeeApi.create(payload);
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
          <h2 className="modal-title">{isEdit ? '직원 정보 수정' : '직원 추가'}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          {/* 기본 정보 */}
          <div className="form-section">
            <h3 className="form-section-title">기본 정보</h3>
            <div className="form-row">
              <div className="form-group form-group--required">
                <label>이름</label>
                <input name="name" value={form.name} onChange={handleChange} placeholder="홍길동" />
              </div>
              <div className="form-group form-group--required">
                <label>구분</label>
                <select name="employee_type" value={form.employee_type} onChange={handleChange}>
                  <option value="PART_TIMER">파트타이머</option>
                  <option value="REGULAR">정규직</option>
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group form-group--required">
                <label>시급 (원)</label>
                <input
                  type="number" name="hourly_wage"
                  value={form.hourly_wage} onChange={handleChange}
                  min={0} placeholder="10030"
                />
              </div>
              <div className="form-group">
                <label>선호 매장</label>
                <select name="preferred_store_id" value={form.preferred_store_id} onChange={handleChange}>
                  <option value="">선택 안 함</option>
                  {stores.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>연락처</label>
                <input name="phone" value={form.phone} onChange={handleChange} placeholder="010-0000-0000" />
              </div>
              <div className="form-group">
                <label>입사일</label>
                <input type="date" name="hire_date" value={form.hire_date} onChange={handleChange} />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>퇴사일</label>
                <input type="date" name="resign_date" value={form.resign_date} onChange={handleChange} />
              </div>
              <div className="form-group" />
            </div>

            <div className="form-group">
              <label>메모</label>
              <textarea name="memo" value={form.memo} onChange={handleChange} rows={2} placeholder="메모를 입력하세요" />
            </div>
          </div>

          {/* 파트타이머 목표 근무시간 */}
          {form.employee_type === 'PART_TIMER' && (
            <div className="form-section">
              <h3 className="form-section-title">월 목표 근무시간 <span className="form-hint">(스케줄 자동 생성 시 활용)</span></h3>
              <div className="form-row form-row--3">
                <div className="form-group">
                  <label>목표 (시간)</label>
                  <input type="number" name="monthly_target_hours" value={form.monthly_target_hours}
                    onChange={handleChange} min={0} placeholder="60" />
                </div>
                <div className="form-group">
                  <label>최소 (시간)</label>
                  <input type="number" name="monthly_min_hours" value={form.monthly_min_hours}
                    onChange={handleChange} min={0} placeholder="40" />
                </div>
                <div className="form-group">
                  <label>최대 (시간)</label>
                  <input type="number" name="monthly_max_hours" value={form.monthly_max_hours}
                    onChange={handleChange} min={0} placeholder="80" />
                </div>
              </div>
            </div>
          )}

          {error && <p className="form-error">{error}</p>}

          <div className="modal-footer">
            <button type="button" className="btn btn--secondary" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn--primary" disabled={saving}>
              {saving ? '저장 중...' : (isEdit ? '수정 완료' : '직원 추가')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
