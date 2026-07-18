import React from 'react';

interface SidebarProps {
  currentPage: string;
  setPage: (page: string) => void;
  isOpen: boolean;
  toggleSidebar: () => void;
  alertCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentPage, setPage, isOpen, toggleSidebar, alertCount }) => {
  return (
    <>
      <div id="mobile-overlay" className={`mobile-overlay ${isOpen ? 'show' : ''}`} onClick={toggleSidebar}></div>
      <aside className={`sidebar ${isOpen ? 'open' : ''}`} id="sidebar">
        <div className="sidebar-logo">
          <div className="flex items-center gap-3">
            <div className="sidebar-logo-icon">
              <i className="fa-solid fa-recycle"></i>
            </div>
            <div>
              <p className="sidebar-logo-title">SmartTrashBin</p>
              <p className="sidebar-logo-subtitle">Hệ thống Thùng rác Thông minh</p>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-nav-group">
            <p className="sidebar-nav-label label-caps">Quản lý</p>

            <a href="#" onClick={(e) => { e.preventDefault(); setPage('dashboard'); toggleSidebar(); }}
               className={`sidebar-link ${currentPage === 'dashboard' ? 'active' : ''}`}>
              <i className="nav-icon fa-solid fa-gauge-high"></i>
              <span>Tổng quan</span>
            </a>

            <a href="#" onClick={(e) => { e.preventDefault(); setPage('bindetail'); toggleSidebar(); }}
               className={`sidebar-link ${currentPage === 'bindetail' ? 'active' : ''}`}>
              <i className="nav-icon fa-solid fa-trash-can"></i>
              <span>Thiết bị</span>
            </a>

            <a href="#" onClick={(e) => { e.preventDefault(); setPage('statistics'); toggleSidebar(); }}
               className={`sidebar-link ${currentPage === 'statistics' ? 'active' : ''}`}>
              <i className="nav-icon fa-solid fa-chart-column"></i>
              <span>Thống kê</span>
            </a>

            <a href="#" onClick={(e) => { e.preventDefault(); setPage('camera'); toggleSidebar(); }}
               className={`sidebar-link ${currentPage === 'camera' ? 'active' : ''}`}>
              <i className="nav-icon fa-solid fa-video"></i>
              <span>Camera</span>
            </a>

            <a href="#" onClick={(e) => { e.preventDefault(); setPage('alerts'); toggleSidebar(); }}
               className={`sidebar-link ${currentPage === 'alerts' ? 'active' : ''}`}>
              <i className="nav-icon fa-solid fa-bell"></i>
              <span>Cảnh báo</span>
              {alertCount > 0 && <span className="nav-badge">{alertCount}</span>}
            </a>

            <a href="#" onClick={(e) => { e.preventDefault(); setPage('config'); toggleSidebar(); }}
               className={`sidebar-link ${currentPage === 'config' ? 'active' : ''}`}>
              <i className="nav-icon fa-solid fa-file-lines"></i>
              <span>Báo cáo</span>
            </a>
          </div>

          <div className="sidebar-divider"></div>

          <div className="sidebar-nav-group">
            <a href="#" className="sidebar-link" style={{ color: 'var(--outline)' }}>
              <i className="nav-icon fa-solid fa-circle-question"></i>
              <span>Hỗ trợ</span>
            </a>
          </div>
        </nav>

        <div className="sidebar-user">
          <div className="flex items-center gap-3">
            <div className="sidebar-user-avatar">A</div>
            <div className="flex-1 min-w-0">
              <p className="sidebar-user-name">Admin</p>
              <p className="sidebar-user-role">Quản trị hệ thống</p>
            </div>
            <i className="fa-solid fa-gear" style={{ color: 'var(--outline)', fontSize: '14px', cursor: 'pointer' }}></i>
          </div>
        </div>
      </aside>
    </>
  );
};
