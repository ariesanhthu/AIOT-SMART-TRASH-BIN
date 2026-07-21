import React, { useState } from 'react';
import type { Bin } from '../types/api';
import { WASTE_TYPES, WASTE_TYPE_KEYS } from '../constants/wasteTypes';
import { useClassifyHistory } from '../hooks/useClassifyHistory';

interface Props {
  bins: Bin[];
}

export const BinDetailPage: React.FC<Props> = ({ bins }) => {
  const [selectedBinId, setSelectedBinId] = useState(bins[0]?.id ?? '');
  const bin = bins.find(b => b.id === selectedBinId) || bins[0];
  const { rows: history } = useClassifyHistory(bin?.id ?? null);

  if (!bin) {
    return <section className="page-section"><p>Chưa có thiết bị nào.</p></section>;
  }

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Chi tiết Thùng rác</h1>
          <p className="subtitle body-md">Giám sát chi tiết từng thùng và ngăn chứa</p>
        </div>
        <select value={selectedBinId} onChange={(e) => setSelectedBinId(e.target.value)} className="input-field" style={{ width: 'auto' }}>
          {bins.map(b => (
            <option key={b.id} value={b.id}>{b.name} — {b.location}</option>
          ))}
        </select>
      </div>

      <div className="card card-padding mb-6">
        <div className="flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-3">
            <div style={{ width: '48px', height: '48px', background: 'var(--primary-fixed)', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-trash-can" style={{ color: 'var(--primary)', fontSize: '20px' }}></i>
            </div>
            <div>
              <p style={{ fontWeight: 700, fontSize: '18px', color: 'var(--on-surface)' }}>{bin.name}</p>
              <p className="body-md" style={{ color: 'var(--outline)' }}>{bin.location}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`status-dot ${bin.online ? 'status-online' : 'status-offline'}`}></span>
            <span className="body-md" style={{ fontWeight: 600, color: bin.online ? 'var(--primary-container)' : 'var(--error)' }}>
              {bin.online ? 'Online' : 'Offline'}
            </span>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 'var(--container-gap)' }}>
        <div className="card card-padding">
          <h2 className="title-sm mb-5" style={{ color: 'var(--on-surface)' }}>Mức đầy từng ngăn</h2>
          <div className="space-y-5">
            {WASTE_TYPE_KEYS.map((k) => {
              const v = bin.compartments[k];
              if (v === undefined) return null;
              const wt = WASTE_TYPES[k];
              const thresh = bin.thresholds[k] ?? 80; // 80 chỉ là fallback nếu backend chưa set threshold cho ngăn này
              const overThresh = v >= thresh;

              return (
                <div key={k}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: wt.color, display: 'inline-block' }}></span>
                      <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Ngăn {wt.label}</span>
                    </div>
                    <span style={{ fontWeight: 700, fontSize: '14px', color: overThresh ? 'var(--error)' : wt.color }}>{v}%{overThresh ? ' — Đầy' : ''}</span>
                  </div>
                  <div className="progress-track" style={{ height: '10px' }}>
                    <div className="progress-fill" style={{ width: `${v}%`, background: overThresh ? '#ef4444' : wt.color, height: '10px', borderRadius: 'var(--radius-full)' }}></div>
                  </div>
                  <div className="flex justify-between mt-1" style={{ fontSize: '11px', color: 'var(--outline)' }}>
                    <span>0%</span>
                    <span style={{ color: overThresh ? 'var(--error)' : 'var(--outline)' }}>Ngưỡng báo: {thresh}%</span>
                    <span>100%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="card">
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #E3E8E1', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Lịch sử phân loại gần nhất</h2>
            <span className="body-md" style={{ color: 'var(--outline)' }}>{history.length} lượt</span>
          </div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Thời gian</th>
                  <th>Loại rác</th>
                  <th>Ngăn mở</th>
                  <th>Kết quả</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row, i) => {
                  const wt = row.wasteType && row.wasteType !== 'REJECTED' ? WASTE_TYPES[row.wasteType] : null;
                  return (
                    <tr key={i}>
                      <td className="font-mono" style={{ fontSize: '13px', color: 'var(--outline)' }}>{row.time}</td>
                      <td>
                        {wt ? (
                          <span className={`badge badge-pill ${wt.bgClass}`}>{wt.label}</span>
                        ) : (
                          <span className="badge badge-pill badge-error">Từ chối</span>
                        )}
                      </td>
                      <td style={{ color: 'var(--outline)' }}>Ngăn {row.compartment}</td>
                      <td>
                        {row.result === 'success' ? (
                          <span className="badge badge-pill badge-success">Thành công</span>
                        ) : (
                          <span className="badge badge-pill badge-error">Từ chối</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
};