import React, { useState } from 'react';
import type { Bin } from '../types/api';
import { Line, Bar } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, BarElement } from 'chart.js';
import { useDailyStats } from '../hooks/useDailyStats';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement);

interface Props {
  bins: Bin[];
}

export const StatisticsPage: React.FC<Props> = ({ bins }) => {
  const [selectedBinId, setSelectedBinId] = useState(bins[0]?.id ?? '');
  const { data, loading } = useDailyStats(selectedBinId || null, 7);

  const totOrg = data.organic.reduce((a, b) => a + b, 0);
  const totRec = data.paper.reduce((a, b) => a + b, 0);
  const totIno = data.plastic.reduce((a, b) => a + b, 0);

  const barData = {
    labels: ['Hữu cơ', 'Giấy', 'Nhựa'],
    datasets: [{
      data: [totOrg, totRec, totIno],
      backgroundColor: ['rgba(34,197,94,0.8)', 'rgba(245,158,11,0.8)', 'rgba(59,130,246,0.8)'],
      borderRadius: 6,
    }]
  };

  const lineData = {
    labels: data.labels,
    datasets: [
      { label: 'Hữu cơ', data: data.organic, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.08)', fill: true, tension: 0.4 },
      { label: 'Giấy', data: data.paper, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)', fill: true, tension: 0.4 },
      { label: 'Nhựa', data: data.plastic, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', fill: true, tension: 0.4 },
    ]
  };

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Báo cáo Thống kê</h1>
          <p className="subtitle body-md">Phân tích xu hướng và hiệu quả phân loại rác</p>
        </div>
        <select value={selectedBinId} onChange={(e) => setSelectedBinId(e.target.value)} className="input-field" style={{ width: 'auto' }}>
          {bins.map(b => (
            <option key={b.id} value={b.id}>{b.name} — {b.location}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <p>Đang tải thống kê...</p>
      ) : (
        <>
          <div className="grid-3 mb-6">
            <div className="card card-padding text-center">
              <p className="kpi-number" style={{ color: 'var(--color-organic)' }}>{totOrg}</p>
              <p className="body-md mt-1" style={{ color: 'var(--outline)' }}>Hữu cơ (lượt)</p>
            </div>
            <div className="card card-padding text-center">
              <p className="kpi-number" style={{ color: 'var(--color-inorganic)' }}>{totRec}</p>
              <p className="body-md mt-1" style={{ color: 'var(--outline)' }}>Giấy (lượt)</p>
            </div>
            <div className="card card-padding text-center">
              <p className="kpi-number" style={{ color: 'var(--color-plastic)' }}>{totIno}</p>
              <p className="body-md mt-1" style={{ color: 'var(--outline)' }}>Nhựa (lượt)</p>
            </div>
          </div>

          <div className="grid-2 mb-6">
            <div className="card card-padding">
              <h2 className="title-sm mb-4" style={{ color: 'var(--on-surface)' }}>Lượng rác theo từng loại</h2>
              <div className="chart-container" style={{ height: '260px' }}>
                <Bar data={barData} options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }} />
              </div>
            </div>
            <div className="card card-padding">
              <h2 className="title-sm mb-4" style={{ color: 'var(--on-surface)' }}>Xu hướng theo ngày</h2>
              <div className="chart-container" style={{ height: '260px' }}>
                <Line data={lineData} options={{ maintainAspectRatio: false }} />
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
};