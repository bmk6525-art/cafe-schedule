import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useMonth } from '../context/MonthContext';
import './MainLayout.css';

const NAV_ITEMS = [
  { to: '/', label: '대시보드', icon: '📊', end: true },
  { to: '/employees', label: '직원 관리', icon: '👥' },
  { to: '/stores', label: '매장 관리', icon: '🏪' },
  { to: '/schedule', label: '스케줄', icon: '📅' },
  { to: '/payroll', label: '급여 관리', icon: '💰' },
  { to: '/monthly', label: '월별 관리', icon: '🗓️' },
  { to: '/history', label: '변경 이력', icon: '📋' },
  { to: '/ai', label: 'AI 어시스턴트', icon: '🤖' },
];

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { year, month, setYearMonth } = useMonth();
  const curYear = new Date().getFullYear();

  return (
    <div className="app-layout">
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar-header">
          <h1 className="sidebar-title">카페 스케줄</h1>
          <p className="sidebar-subtitle">근무 관리 시스템</p>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'nav-item--active' : ''}`
              }
              onClick={() => setSidebarOpen(false)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-month">
          <p className="sidebar-month-label">기준 월</p>
          <div className="sidebar-month-selects">
            <select
              value={year}
              onChange={(e) => setYearMonth(Number(e.target.value), month)}
            >
              {[curYear - 1, curYear, curYear + 1].map((y) => (
                <option key={y} value={y}>{y}년</option>
              ))}
            </select>
            <select
              value={month}
              onChange={(e) => setYearMonth(year, Number(e.target.value))}
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>{m}월</option>
              ))}
            </select>
          </div>
        </div>
        <div className="sidebar-footer">
          <p>PHASE 14 완료 · v1.0.0</p>
        </div>
      </aside>

      <main className="main-content">
        <button
          className="mobile-menu-btn"
          onClick={() => setSidebarOpen(true)}
          aria-label="메뉴 열기"
        >
          ☰
        </button>
        <Outlet />
      </main>
    </div>
  );
}
