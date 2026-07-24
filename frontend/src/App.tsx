import { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { DashboardPage } from './pages/DashboardPage';
import { AlertsPage } from './pages/AlertsPage';
import { StatisticsPage } from './pages/StatisticsPage';
import { BinDetailPage } from './pages/BinDetailPage';
import { ConfigPage } from './pages/ConfigPage';
import { CameraPage } from './pages/CameraPage';
import { LoginPage } from './pages/LoginPage';
import { useBins } from './hooks/useBins';
import { useFullAlerts } from './hooks/useFullAlerts';
import { useAuthUser } from './hooks/useAuthUser';
import { SupportPage } from './pages/SupportPage';
import './index.css';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState('');

  const { user, loading: authLoading, logout } = useAuthUser();
  const { bins, loading: binsLoading, reload: reloadBins } = useBins();
  const { alerts, resolveAlert, markAllResolved } = useFullAlerts(bins);

  const pendingAlertCount = alerts.filter((a) => a.status === 'pending').length;

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(''), 2800);
  };

  // Chờ Firebase xác định xong trạng thái đăng nhập trước khi quyết định
  // hiện Login hay Dashboard — tránh nháy màn hình Login rồi bật lại Dashboard.
  if (authLoading) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100vh',
        gap: 12,
        color: 'var(--on-surface)',
      }}>
        <i className="fa-solid fa-spinner fa-spin" style={{ fontSize: 28 }}></i>
        <span>Đang kiểm tra đăng nhập...</span>
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  if (binsLoading) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100vh',
        gap: 12,
        color: 'var(--on-surface)',
      }}>
        <i className="fa-solid fa-spinner fa-spin" style={{ fontSize: 28 }}></i>
        <span>Đang tải dữ liệu thiết bị...</span>
      </div>
    );
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage bins={bins} alerts={alerts} setPage={setCurrentPage} />;
      case 'bindetail':
        return <BinDetailPage bins={bins} />;
      case 'statistics':
        return <StatisticsPage bins={bins} />;
      case 'alerts':
        return (
          <AlertsPage
            alerts={alerts}
            resolveAlert={resolveAlert}
            markAllResolved={markAllResolved}
            showToast={showToast}
          />
        );
      case 'config':
        return <ConfigPage bins={bins} reloadBins={reloadBins} showToast={showToast} />;
      case 'camera':
        return <CameraPage />;
      case 'support':
        return <SupportPage />;
      default:
        return <DashboardPage bins={bins} alerts={alerts} setPage={setCurrentPage} />;
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
        userEmail={user.email ?? 'Admin'}
        onLogout={logout}
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
