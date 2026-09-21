import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { MonthProvider } from './context/MonthContext';
import MainLayout from './layouts/MainLayout';
import Dashboard from './pages/Dashboard';
import Employees from './pages/Employees';
import Stores from './pages/Stores';
import Schedule from './pages/Schedule';
import Payroll from './pages/Payroll';
import MonthlyManage from './pages/MonthlyManage';
import History from './pages/History';
import AIAssistant from './pages/AIAssistant';

export default function App() {
  return (
    <MonthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="employees" element={<Employees />} />
            <Route path="stores" element={<Stores />} />
            <Route path="schedule" element={<Schedule />} />
            <Route path="payroll" element={<Payroll />} />
            <Route path="monthly" element={<MonthlyManage />} />
            <Route path="history" element={<History />} />
            <Route path="ai" element={<AIAssistant />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </MonthProvider>
  );
}
