// ───────────────────────────────────────────────
// 공통 타입 정의
// ───────────────────────────────────────────────

export type EmployeeType = 'REGULAR' | 'PART_TIMER';

export type DayOfWeek = 'MON' | 'TUE' | 'WED' | 'THU' | 'FRI' | 'SAT' | 'SUN';

export type ScheduleStatus = 'DRAFT' | 'CONFIRMED' | 'LOCKED';

export interface Store {
  id: number;
  name: string;
  open_time: string;
  close_time: string;
  is_active: boolean;
  memo?: string;
  created_at: string;
  updated_at: string;
}

export interface Employee {
  id: number;
  name: string;
  employee_type: EmployeeType;
  hourly_wage: number;
  phone?: string;
  hire_date?: string;
  resign_date?: string;
  is_active: boolean;
  preferred_store_id?: number;
  memo?: string;
  monthly_target_hours?: number;
  monthly_min_hours?: number;
  monthly_max_hours?: number;
  created_at: string;
  updated_at: string;
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
  success?: boolean;
}

export interface MessageResponse {
  message: string;
  success: boolean;
}

export interface WorkPattern {
  id: number;
  employee_id: number;
  day_of_week: DayOfWeek;
  is_day_off: boolean;
  start_time: string | null;
  end_time: string | null;
  store_id: number | null;
}

export const DAY_LABELS: Record<DayOfWeek, string> = {
  MON: '월',
  TUE: '화',
  WED: '수',
  THU: '목',
  FRI: '금',
  SAT: '토',
  SUN: '일',
};

export const DAY_ORDER: DayOfWeek[] = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
