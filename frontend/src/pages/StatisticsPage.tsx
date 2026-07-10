import React from 'react';
import { DAILY_DATA } from '../data';
import { Line, Bar } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, BarElement } from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement);

export const StatisticsPage: React.FC = () => {
  const totOrg = DAILY_DATA.organic.reduce((a, b) => a + b, 0);
  const totRec = DAILY_DATA.recycle.reduce((a, b) => a + b, 0);
  const totIno = DAILY_DATA.inorganic.reduce((a, b) => a + b, 0);

  const barData = {
    labels: ['Hữu cơ', 'Nhựa', 'Giấy'],
    datasets: [{
      data: [totOrg, totRec, totIno],
      backgroundColor: ['rgba(34,197,94,0.8)', 'rgba(59,130,246,0.8)', 'rgba(245,158,11,0.8)'],
      borderRadius: 6,
    }]
  };

  const lineData = {
    labels: DAILY_DATA.labels,
    datasets: [
      { label: 'Hữu cơ', data: DAILY_DATA.organic, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.08)', fill: true, tension: 0.4 },
      { label: 'Nhựa', data: DAILY_DATA.recycle, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', fill: true, tension: 0.4 },
      { label: 'Giấy', data: DAILY_DATA.inorganic, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)', fill: true, tension: 0.4 },
    ]
  };

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Báo cáo Thống kê</h1>
          <p className="subtitle body-md">Phân tích xu hướng và hiệu quả phân loại rác</p>
        </div>
      </div>

      <div className="grid-3 mb-6">
        <div className="card card-padding text-center">
          <p className="kpi-number" style={{ color: 'var(--color-organic)' }}>{totOrg}</p>
          <p className="body-md mt-1" style={{ color: 'var(--outline)' }}>Hữu cơ (lượt)</p>
        </div>
        <div className="card card-padding text-center">
          <p className="kpi-number" style={{ color: 'var(--color-plastic)' }}>{totRec}</p>
          <p className="body-md mt-1" style={{ color: 'var(--outline)' }}>Tái chế (lượt)</p>
        </div>
        <div className="card card-padding text-center">
          <p className="kpi-number" style={{ color: 'var(--color-inorganic)' }}>{totIno}</p>
          <p className="body-md mt-1" style={{ color: 'var(--outline)' }}>Vô cơ (lượt)</p>
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
    </section>
  );
};
