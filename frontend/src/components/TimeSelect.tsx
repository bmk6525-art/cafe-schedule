/**
 * 커스텀 시간 선택기 — 시(0~23) + 분(5분 단위)
 * native <input type="time"> 대신 사용하여:
 *   1. 모달 닫힘 버그 방지 (React DOM 이벤트만 사용)
 *   2. 5분 단위 강제 적용
 */

import './TimeSelect.css';

const MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

interface Props {
  value: string;           // "HH:MM"
  onChange: (v: string) => void;
  disabled?: boolean;
  className?: string;
}

export default function TimeSelect({ value, onChange, disabled = false, className = '' }: Props) {
  const parts = (value || '09:00').split(':');
  const hour = Math.min(23, Math.max(0, parseInt(parts[0] ?? '9', 10)));
  // 분은 5분 단위로 반올림
  const rawMin = parseInt(parts[1] ?? '0', 10);
  const minute = Math.floor(rawMin / 5) * 5;

  function onHourChange(e: React.ChangeEvent<HTMLSelectElement>) {
    e.stopPropagation();
    onChange(`${String(Number(e.target.value)).padStart(2, '0')}:${String(minute).padStart(2, '0')}`);
  }

  function onMinChange(e: React.ChangeEvent<HTMLSelectElement>) {
    e.stopPropagation();
    onChange(`${String(hour).padStart(2, '0')}:${String(Number(e.target.value)).padStart(2, '0')}`);
  }

  return (
    <div
      className={`time-select${disabled ? ' time-select--disabled' : ''} ${className}`}
      onClick={(e) => e.stopPropagation()}
    >
      <select
        className="time-select__hour"
        value={hour}
        disabled={disabled}
        onChange={onHourChange}
      >
        {HOURS.map((h) => (
          <option key={h} value={h}>{String(h).padStart(2, '0')}</option>
        ))}
      </select>
      <span className="time-select__sep">:</span>
      <select
        className="time-select__min"
        value={minute}
        disabled={disabled}
        onChange={onMinChange}
      >
        {MINUTES.map((m) => (
          <option key={m} value={m}>{String(m).padStart(2, '0')}</option>
        ))}
      </select>
    </div>
  );
}
