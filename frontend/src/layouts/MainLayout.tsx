import { NavLink, Outlet } from 'react-router-dom';
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
  return (
    <div className="app-layout">
      <aside className="sidebar">
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
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <p>PHASE 14 완료 · v1.0.0</p>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
