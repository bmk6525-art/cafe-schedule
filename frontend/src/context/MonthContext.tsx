import { createContext, useContext, useState, ReactNode } from 'react';

interface MonthCtx {
  year: number;
  month: number;
  setYearMonth: (y: number, m: number) => void;
}

const MonthContext = createContext<MonthCtx | null>(null);
const LS_KEY = 'cafe_working_month';

function loadSaved(): { year: number; month: number } {
  try {
    const s = localStorage.getItem(LS_KEY);
    if (s) {
      const p = JSON.parse(s);
      if (p.year && p.month) return p;
    }
  } catch {}
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

export function MonthProvider({ children }: { children: ReactNode }) {
  const init = loadSaved();
  const [year, setYear] = useState(init.year);
  const [month, setMonth] = useState(init.month);

  function setYearMonth(y: number, m: number) {
    setYear(y);
    setMonth(m);
    localStorage.setItem(LS_KEY, JSON.stringify({ year: y, month: m }));
  }

  return (
    <MonthContext.Provider value={{ year, month, setYearMonth }}>
      {children}
    </MonthContext.Provider>
  );
}

export function useMonth(): MonthCtx {
  const ctx = useContext(MonthContext);
  if (!ctx) throw new Error('useMonth must be used within MonthProvider');
  return ctx;
}
