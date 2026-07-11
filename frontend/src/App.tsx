import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { DashboardPage } from './pages/DashboardPage';
import { AlertsPage } from './pages/AlertsPage';
import { StatisticsPage } from './pages/StatisticsPage';
import { BinDetailPage } from './pages/BinDetailPage';
import { ConfigPage } from './pages/ConfigPage';
import { ALERT_HISTORY, BINS } from './data';
import './index.css';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState('');
  const [bins, setBins] = useState(BINS);
  const [alerts, setAlerts] = useState(ALERT_HISTORY);

  const pendingAlertCount = alerts.filter(a => a.status === 'pending').length;

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(''), 2800);
  };

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage bins={bins} alerts={alerts} setPage={setCurrentPage} showToast={showToast} />;
      case 'bindetail':
        return <BinDetailPage bins={bins} />;
      case 'statistics':
        return <StatisticsPage />;
      case 'alerts':
        return <AlertsPage alerts={alerts} setAlerts={setAlerts} showToast={showToast} />;
      case 'config':
        return <ConfigPage showToast={showToast} />;
      default:
        return <DashboardPage bins={bins} alerts={alerts} setPage={setCurrentPage} showToast={showToast} />;
    }
  };

  return (
    <>
      <div id="toast" className={`toast ${toastMsg ? 'visible' : ''}`}>
        <i className="fa-solid fa-circle-check"></i>
        <span>{toastMsg}</span>
      </div>

      <Sidebar 
        currentPage={currentPage} 
        setPage={setCurrentPage} 
        isOpen={sidebarOpen} 
        toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        alertCount={pendingAlertCount}
      />

      <main className="main-canvas">
        <div className="mobile-toggle" style={{ padding: '12px 16px', background: 'var(--surface-container-lowest)', borderBottom: '1px solid #E3E8E1' }}>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '18px', color: 'var(--on-surface)' }}>
            <i className="fa-solid fa-bars"></i>
          </button>
        </div>
        {renderPage()}
      </main>
    </>
  );
}

export default App;
