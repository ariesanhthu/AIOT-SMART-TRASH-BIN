import React, { useMemo } from 'react';
import { type Bin, WASTE_TYPES, REWARDS, ALERT_HISTORY } from '../data';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';

ChartJS.register(ArcElement, Tooltip, Legend);

interface Props {
  bins: Bin[];
  alerts: typeof ALERT_HISTORY;
  setPage: (page: string) => void;
}

export const DashboardPage: React.FC<Props> = ({ bins, alerts, setPage }) => {
  const fullBins = useMemo(() => bins.filter(b => Object.values(b.compartments).some(v => v >= 80)).length, [bins]);
  const onlineBins = useMemo(() => bins.filter(b => b.online).length, [bins]);
  const dashBins = bins.slice(0, 4);
  const pendingAlerts = useMemo(() => alerts.filter(a => a.status === 'pending').slice(0, 3), [alerts]);

  const chartData = {
    labels: ['Nhựa', 'Giấy', 'Hữu cơ'],
    datasets: [{
      data: [35, 40, 25],
      backgroundColor: ['#3b82f6', '#f59e0b', '#22c55e'],
      borderWidth: 0,
      hoverOffset: 6,
    }]
  };

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Tổng quan hệ thống</h1>
          <p className="subtitle body-md">Theo dõi trạng thái thùng rác thông minh theo thời gian thực</p>
        </div>
        <div className="page-header-actions">
          <div className="filter-group">
            <button className="time-btn active-time">Hôm nay</button>
            <button className="time-btn">7 ngày</button>
            <button className="time-btn">30 ngày</button>
          </div>
        </div>
      </div>

      <div className="grid-4 mb-6">
        <div className="card card-padding stat-card">
          <div className="flex items-start justify-between">
            <div>
              <p className="label-caps" style={{ color: 'var(--outline)' }}>Tổng lượt bỏ rác</p>
              <p className="kpi-number mt-1" style={{ color: 'var(--on-surface)' }}>128</p>
            </div>
            <div className="stat-icon-wrap" style={{ background: 'var(--surface-container)' }}>
              <i className="fa-solid fa-trash-can" style={{ color: 'var(--outline)' }}></i>
            </div>
          </div>
        </div>

        <div className="card card-padding stat-card">
          <div className="flex items-start justify-between">
            <div>
              <p className="label-caps" style={{ color: 'var(--outline)' }}>Rác tái chế</p>
              <p className="kpi-number mt-1" style={{ color: 'var(--on-surface)' }}>86</p>
            </div>
            <div className="stat-icon-wrap" style={{ background: '#dbeafe' }}>
              <i className="fa-solid fa-recycle" style={{ color: 'var(--color-plastic)' }}></i>
            </div>
          </div>
        </div>

        <div className="card card-padding stat-card">
          <div className="flex items-start justify-between">
            <div>
              <p className="label-caps" style={{ color: 'var(--outline)' }}>Cần xử lý</p>
              <p className="kpi-number mt-1" style={{ color: 'var(--error)' }}>{fullBins}</p>
            </div>
            <div className="stat-icon-wrap" style={{ background: 'var(--error-container)' }}>
              <i className="fa-solid fa-triangle-exclamation" style={{ color: 'var(--error)' }}></i>
            </div>
          </div>
        </div>

        <div className="card card-padding stat-card">
          <div className="flex items-start justify-between">
            <div>
              <p className="label-caps" style={{ color: 'var(--outline)' }}>Thiết bị online</p>
              <p className="kpi-number mt-1" style={{ color: 'var(--on-surface)' }}>
                <span style={{ color: 'var(--primary-container)' }}>{onlineBins}</span>
                <span style={{ fontSize: '20px', color: 'var(--outline)' }}>/{bins.length}</span>
              </p>
            </div>
            <div className="stat-icon-wrap" style={{ background: '#dcfce7' }}>
              <i className="fa-solid fa-wifi" style={{ color: 'var(--primary-container)' }}></i>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 340px', gap: 'var(--container-gap)', marginBottom: 'var(--container-gap)' }}>
        <div style={{ gridColumn: 'span 2' }}>
          <div className="section-header">
            <h2 className="section-title">Trạng thái thiết bị</h2>
            <a href="#" onClick={(e) => { e.preventDefault(); setPage('bindetail'); }} style={{ fontSize: '13px', color: 'var(--primary-container)', textDecoration: 'none', fontWeight: 500 }}>
              Xem tất cả <i className="fa-solid fa-arrow-right" style={{ fontSize: '10px' }}></i>
            </a>
          </div>
          <div className="grid-2">
            {dashBins.map(bin => {
              return (
                <div key={bin.id} onClick={() => setPage('bindetail')} className="card card-padding card-interactive" style={{ position: 'relative' }}>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <p className="title-sm" style={{ color: 'var(--on-surface)' }}>{bin.name}</p>
                      <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                        <i className="fa-solid fa-location-dot" style={{ fontSize: '10px' }}></i> {bin.location}
                      </p>
                    </div>
                    <span className={`badge badge-pill ${bin.online ? 'badge-online' : 'badge-offline'}`} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: bin.online ? '#22c55e' : 'var(--error)', display: 'inline-block' }}></span>
                      {bin.online ? 'Online' : 'Offline'}
                    </span>
                  </div>
                  {bin.online ? (
                    <div className="space-y-3" style={{ marginTop: '12px' }}>
                      {Object.entries(bin.compartments).map(([k, v]) => {
                        const wt = WASTE_TYPES[k as keyof typeof WASTE_TYPES];
                        const isOver = v >= 80;
                        return (
                          <div key={k}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="body-md" style={{ fontSize: '12px', color: 'var(--on-surface)' }}>{wt.label}</span>
                              <span className="body-md" style={{ fontSize: '12px', fontWeight: 600, color: isOver ? 'var(--error)' : 'var(--on-surface)' }}>{v}%</span>
                            </div>
                            <div className="progress-track">
                              <div className="progress-fill" style={{ width: `${v}%`, background: isOver ? '#ef4444' : wt.color }}></div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', padding: '16px 0' }}>
                      <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: 'var(--surface-container)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <i className="fa-solid fa-wifi" style={{ color: 'var(--outline-variant)', fontSize: '16px', opacity: 0.5 }}></i>
                      </div>
                      <p className="body-md" style={{ color: 'var(--outline-variant)' }}>Mất kết nối</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--container-gap)' }}>
          <div>
            <div className="section-header">
              <h2 className="section-title">Cảnh báo gần đây</h2>
            </div>
            <div className="card">
              <div className="space-y-0">
                {pendingAlerts.length === 0 ? (
                  <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--outline)' }}>
                    <p className="body-md">Không có cảnh báo</p>
                  </div>
                ) : (
                  pendingAlerts.map(a => (
                    <div key={a.id} style={{ padding: '16px 20px', borderBottom: '1px solid #E3E8E1', display: 'flex', gap: '12px' }}>
                      <div style={{ width: '36px', height: '36px', borderRadius: 'var(--radius)', background: 'var(--error-container)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <i className="fa-solid fa-triangle-exclamation" style={{ color: 'var(--error)', fontSize: '14px' }}></i>
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)', fontSize: '13px' }}>
                          Khẩn cấp Bin {a.bin} — {a.compartment}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
          <div>
            <div className="section-header">
              <h2 className="section-title">Bảng điểm thưởng</h2>
            </div>
            <div className="card card-padding">
              <div className="space-y-4">
                {REWARDS.map((r, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span style={{ fontSize: '18px', minWidth: '24px', textAlign: 'center' }}>{i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : ''}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="flex items-center justify-between" style={{ marginBottom: '6px' }}>
                        <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>{r.name}</span>
                        <span className="body-md" style={{ fontWeight: 700, fontSize: '13px' }}>{r.points} đ</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 'var(--container-gap)' }}>
        <div className="card card-padding">
          <h2 className="section-title mb-4">Phân loại rác hôm nay</h2>
          <div className="chart-container" style={{ height: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Doughnut data={chartData} options={{ maintainAspectRatio: false, plugins: { legend: { display: false } }, cutout: '65%' }} />
          </div>
        </div>
      </div>
    </section>
  );
};
