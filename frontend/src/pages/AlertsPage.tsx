import React, { useState } from 'react';
import { WASTE_TYPES } from '../constants/wasteTypes';
import type { AlertRow } from '../types/api';

interface Props {
  alerts: AlertRow[];
  resolveAlert: (id: string) => void;
  markAllResolved: () => void;
  showToast: (msg: string) => void;
}

export const AlertsPage: React.FC<Props> = ({ alerts, resolveAlert, markAllResolved, showToast }) => {
  const activeAlerts = alerts.filter(a => a.status === 'pending');
  const [filter, setFilter] = useState('all');

  const handleResolve = (id: string) => {
    resolveAlert(id);
    showToast('Đã đánh dấu đã xử lý!');
  };

  const handleMarkAll = () => {
    markAllResolved();
    showToast('Tất cả cảnh báo đã xử lý!');
  };

  const filteredAlerts = alerts.filter(a => filter === 'all' || a.status === filter);

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Hệ thống Cảnh báo</h1>
          <p className="subtitle body-md">Theo dõi và xử lý cảnh báo thời gian thực</p>
        </div>
      </div>

      <div className="card mb-6">
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #E3E8E1', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="flex items-center gap-2">
            <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Cảnh báo đang hoạt động</h2>
            <span className="badge badge-pill badge-error">{activeAlerts.length} cảnh báo</span>
          </div>
          <button onClick={handleMarkAll} className="btn btn-outline btn-sm">
            <i className="fa-solid fa-check-double" style={{ fontSize: '12px' }}></i> Đánh dấu tất cả
          </button>
        </div>
        <div style={{ maxHeight: '288px', overflowY: 'auto' }}>
          {activeAlerts.length === 0 ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--outline)' }}>
              <i className="fa-solid fa-circle-check" style={{ fontSize: '24px', color: 'var(--primary-container)', marginBottom: '8px', display: 'block' }}></i>
              <p className="body-md">Không có cảnh báo nào đang hoạt động</p>
            </div>
          ) : (
            activeAlerts.map(a => {
              const wt = WASTE_TYPES[a.type];
              return (
                <div key={a.id} style={{ padding: '14px 20px', display: 'flex', alignItems: 'center', gap: '14px', borderBottom: '1px solid #E3E8E1' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--error)', flexShrink: 0 }}></div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Ngăn {a.compartment} — Bin {a.bin}</p>
                    <p style={{ fontSize: '12px', color: 'var(--outline)', marginTop: '2px' }}>{a.date} · {a.time}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`badge badge-pill ${wt.bgClass}`}>{wt.label}</span>
                    <span style={{ fontWeight: 700, color: a.fill >= 90 ? 'var(--error)' : '#d97706', fontSize: '14px' }}>{a.fill}%</span>
                    <button onClick={() => handleResolve(a.id)} className="btn btn-sm" style={{ background: 'var(--primary-fixed)', color: 'var(--primary)', border: 'none' }}>
                      Xử lý
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      <div className="card">
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #E3E8E1', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
          <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Lịch sử cảnh báo</h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="input-field" style={{ width: 'auto', padding: '6px 12px', fontSize: '13px' }}>
            <option value="all">Tất cả</option>
            <option value="resolved">Đã xử lý</option>
            <option value="pending">Chưa xử lý</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Thùng / Ngăn</th>
                <th>Loại rác</th>
                <th>Độ đầy</th>
                <th>Thời gian</th>
                <th>Trạng thái</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filteredAlerts.map(a => {
                const wt = WASTE_TYPES[a.type];
                return (
                  <tr key={a.id}>
                    <td>
                      <p style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Bin {a.bin}</p>
                      <p style={{ fontSize: '12px', color: 'var(--outline)' }}>Ngăn {a.compartment}</p>
                    </td>
                    <td><span className={`badge badge-pill ${wt.bgClass}`}>{wt.label}</span></td>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="progress-track" style={{ width: '64px' }}>
                          <div className="progress-fill" style={{ width: `${a.fill}%`, background: a.fill >= 85 ? 'var(--error)' : a.fill >= 70 ? '#d97706' : '#22c55e' }}></div>
                        </div>
                        <span style={{ fontWeight: 600, fontSize: '13px', color: a.fill >= 85 ? 'var(--error)' : a.fill >= 70 ? '#d97706' : 'var(--primary-container)' }}>{a.fill}%</span>
                      </div>
                    </td>
                    <td style={{ color: 'var(--outline)' }}>{a.date}<br /><span style={{ fontSize: '12px' }}>{a.time}</span></td>
                    <td>
                      {a.status === 'resolved' ? (
                        <span className="badge badge-pill badge-success">Đã xử lý</span>
                      ) : (
                        <span className="badge badge-pill badge-error">Chưa xử lý</span>
                      )}
                    </td>
                    <td>
                      {a.status === 'pending' && (
                        <button onClick={() => handleResolve(a.id)} style={{ fontSize: '13px', color: 'var(--primary-container)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 500, fontFamily: 'Manrope' }}>Xử lý</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};