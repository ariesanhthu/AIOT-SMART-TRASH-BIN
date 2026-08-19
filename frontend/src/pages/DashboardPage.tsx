import React, { useMemo, useState } from 'react';
import { Chart as ChartJS, ArcElement, Tooltip } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import { useRanking } from '../hooks/useRanking';
import { useTodaySummary } from '../hooks/useTodaySummary';
import type { AlertRow, Bin } from '../types/api';
import { WASTE_TYPE_KEYS, WASTE_TYPES, type WasteTypeKey } from '../constants/wasteTypes';
import { getConfiguredThreshold } from '../utils/thresholds';

ChartJS.register(ArcElement, Tooltip);

interface Props {
  bins: Bin[];
  alerts: AlertRow[];
  setPage: (page: string) => void;
}

const PERIOD_OPTIONS = [
  { days: 1, label: 'Hôm nay', chartTitle: 'Hôm nay' },
  { days: 7, label: '7 ngày', chartTitle: '7 ngày qua' },
  { days: 30, label: '30 ngày', chartTitle: '30 ngày qua' },
] as const;

const NUMBER_FORMATTER = new Intl.NumberFormat('vi-VN');

function countFullCompartments(bins: Bin[]): number {
  return bins.reduce((total, bin) => {
    const fullInBin = WASTE_TYPE_KEYS.reduce((count, key) => {
      const fill = bin.compartments[key] ?? 0;
      const threshold = getConfiguredThreshold(bin.thresholds, key);
      return count + (threshold !== null && fill >= threshold ? 1 : 0);
    }, 0);
    return total + fullInBin;
  }, 0);
}

function wasteLabel(type: WasteTypeKey): string {
  return WASTE_TYPES[type].label;
}

export const DashboardPage: React.FC<Props> = ({ bins, alerts, setPage }) => {
  const [days, setDays] = useState(1);
  const { summary, loading: summaryLoading } = useTodaySummary(days);
  const ranking = useRanking(bins, days);

  const onlineBins = useMemo(() => bins.filter((bin) => bin.online).length, [bins]);
  const fullCompartments = useMemo(() => countFullCompartments(bins), [bins]);
  const pendingAlerts = useMemo(
    () => alerts.filter((alert) => alert.status === 'pending').slice(0, 4),
    [alerts],
  );
  const period = PERIOD_OPTIONS.find((option) => option.days === days) ?? PERIOD_OPTIONS[0];

  const chartValues = useMemo(
    () => [summary.organicCount, summary.paperCount, summary.plasticCount],
    [summary.organicCount, summary.paperCount, summary.plasticCount],
  );
  const chartTotal = chartValues.reduce((total, count) => total + count, 0);
  const chartData = useMemo(
    () => ({
      labels: WASTE_TYPE_KEYS.map(wasteLabel),
      datasets: [
        {
          data: chartValues,
          backgroundColor: WASTE_TYPE_KEYS.map((key) => WASTE_TYPES[key].color),
          borderColor: '#ffffff',
          borderWidth: 4,
          hoverBorderWidth: 4,
          hoverOffset: 7,
          spacing: 2,
        },
      ],
    }),
    [chartValues],
  );

  return (
    <section className="page-section dashboard-page">
      <header className="dashboard-hero">
        <div>
          <p className="dashboard-eyebrow">Trung tâm vận hành</p>
          <h1>Tổng quan hệ thống</h1>
          <p className="dashboard-subtitle">
            Theo dõi thiết bị, sức chứa và hoạt động phân loại trên một màn hình.
          </p>
        </div>

        <div className="dashboard-period" aria-label="Khoảng thời gian thống kê">
          {PERIOD_OPTIONS.map((option) => (
            <button
              key={option.days}
              type="button"
              className={`dashboard-period__button ${days === option.days ? 'is-active' : ''}`}
              aria-pressed={days === option.days}
              onClick={() => setDays(option.days)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      <div className="dashboard-kpi-grid" aria-live="polite" aria-busy={summaryLoading}>
        <article className="dashboard-kpi dashboard-kpi--primary">
          <div className="dashboard-kpi__icon" aria-hidden="true">
            <i className="fa-solid fa-trash-can" />
          </div>
          <div>
            <p className="dashboard-kpi__label">Tổng lượt bỏ rác</p>
            <p className="dashboard-kpi__value">
              {summaryLoading ? '—' : NUMBER_FORMATTER.format(summary.totalCount)}
            </p>
            <p className="dashboard-kpi__meta">{period.chartTitle}</p>
          </div>
        </article>

        <article className="dashboard-kpi dashboard-kpi--blue">
          <div className="dashboard-kpi__icon" aria-hidden="true">
            <i className="fa-solid fa-recycle" />
          </div>
          <div>
            <p className="dashboard-kpi__label">Rác tái chế</p>
            <p className="dashboard-kpi__value">
              {summaryLoading ? '—' : NUMBER_FORMATTER.format(summary.recyclableCount)}
            </p>
            <p className="dashboard-kpi__meta">Giấy và nhựa</p>
          </div>
        </article>

        <article className="dashboard-kpi dashboard-kpi--red">
          <div className="dashboard-kpi__icon" aria-hidden="true">
            <i className="fa-solid fa-triangle-exclamation" />
          </div>
          <div>
            <p className="dashboard-kpi__label">Cần xử lý</p>
            <p className="dashboard-kpi__value">{NUMBER_FORMATTER.format(fullCompartments)}</p>
            <p className="dashboard-kpi__meta">Ngăn đạt ngưỡng đầy</p>
          </div>
        </article>

        <article className="dashboard-kpi dashboard-kpi--green">
          <div className="dashboard-kpi__icon" aria-hidden="true">
            <i className="fa-solid fa-wifi" />
          </div>
          <div>
            <p className="dashboard-kpi__label">Thiết bị online</p>
            <p className="dashboard-kpi__value">
              {onlineBins}<span className="dashboard-kpi__denominator">/{bins.length}</span>
            </p>
            <p className="dashboard-kpi__meta">
              {bins.length === 0 ? 'Chưa có thiết bị' : `${bins.length - onlineBins} thiết bị offline`}
            </p>
          </div>
        </article>
      </div>

      <div className="dashboard-main-grid">
        <section className="dashboard-panel dashboard-devices-panel" aria-labelledby="devices-title">
          <div className="dashboard-panel__header">
            <div>
              <p className="dashboard-panel__eyebrow">Giám sát trực tiếp</p>
              <h2 id="devices-title">Trạng thái thiết bị</h2>
            </div>
            <button type="button" className="dashboard-text-button" onClick={() => setPage('bindetail')}>
              Xem tất cả <i className="fa-solid fa-arrow-right" aria-hidden="true" />
            </button>
          </div>

          {bins.length === 0 ? (
            <div className="dashboard-empty-state">
              <i className="fa-solid fa-trash-can" aria-hidden="true" />
              <p>Chưa có thiết bị trên server local.</p>
            </div>
          ) : (
            <div className="dashboard-device-grid">
              {bins.slice(0, 4).map((bin) => (
                <button
                  key={bin.id}
                  type="button"
                  className="dashboard-device-card"
                  onClick={() => setPage('bindetail')}
                >
                  <span className="dashboard-device-card__header">
                    <span className="dashboard-device-card__identity">
                      <span className="dashboard-device-card__icon" aria-hidden="true">
                        <i className="fa-solid fa-trash-can" />
                      </span>
                      <span className="dashboard-device-card__name-wrap">
                        <strong>{bin.name}</strong>
                        <span><i className="fa-solid fa-location-dot" aria-hidden="true" /> {bin.location}</span>
                      </span>
                    </span>
                    <span className={`dashboard-status ${bin.online ? 'is-online' : 'is-offline'}`}>
                      <span aria-hidden="true" />
                      {bin.online ? 'Online' : 'Offline'}
                    </span>
                  </span>

                  {!bin.online ? (
                    <span className="dashboard-device-card__notice">
                      Dữ liệu local gần nhất
                    </span>
                  ) : null}

                  <span className="dashboard-compartments">
                    {WASTE_TYPE_KEYS.map((key) => {
                      const value = bin.compartments[key] ?? 0;
                      const threshold = getConfiguredThreshold(bin.thresholds, key);
                      const isOver = threshold !== null && value >= threshold;
                      return (
                        <span className="dashboard-compartment" key={key}>
                          <span className="dashboard-compartment__meta">
                            <span>{wasteLabel(key)}</span>
                            <strong className={isOver ? 'is-over' : ''}>
                              {value}%{isOver ? <span className="dashboard-full-label">Đầy</span> : null}
                            </strong>
                          </span>
                          <span
                            className="dashboard-compartment__track"
                            role="progressbar"
                            aria-label={`${wasteLabel(key)} ${value}%`}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={value}
                          >
                            <span
                              className="dashboard-compartment__fill"
                              style={{ width: `${Math.min(100, Math.max(0, value))}%`, background: isOver ? '#dc2626' : WASTE_TYPES[key].color }}
                            />
                          </span>
                        </span>
                      );
                    })}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="dashboard-panel dashboard-chart-panel" aria-labelledby="chart-title">
          <div className="dashboard-panel__header">
            <div>
              <p className="dashboard-panel__eyebrow">Cơ cấu phân loại</p>
              <h2 id="chart-title">{period.chartTitle}</h2>
            </div>
            {summaryLoading ? <span className="dashboard-loading">Đang cập nhật…</span> : null}
          </div>

          {chartTotal === 0 && !summaryLoading ? (
            <div className="dashboard-empty-state dashboard-empty-state--chart">
              <i className="fa-solid fa-chart-pie" aria-hidden="true" />
              <strong>Chưa có lượt phân loại</strong>
              <p>Biểu đồ sẽ cập nhật khi server local nhận dữ liệu trong {period.chartTitle.toLowerCase()}.</p>
            </div>
          ) : (
            <>
              <div className="dashboard-donut">
                <Doughnut
                  key={days}
                  data={chartData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '72%',
                    animation: { duration: 350 },
                    plugins: {
                      tooltip: {
                        callbacks: {
                          label: (context) => ` ${context.label}: ${NUMBER_FORMATTER.format(Number(context.raw))} lượt`,
                        },
                      },
                    },
                  }}
                />
                <div className="dashboard-donut__center" aria-hidden="true">
                  <strong>{NUMBER_FORMATTER.format(chartTotal)}</strong>
                  <span>lượt phân loại</span>
                </div>
              </div>

              <div className="dashboard-chart-legend">
                {WASTE_TYPE_KEYS.map((key, index) => (
                  <div key={key} className="dashboard-chart-legend__item">
                    <span className="dashboard-chart-legend__dot" style={{ background: WASTE_TYPES[key].color }} />
                    <span>{wasteLabel(key)}</span>
                    <strong>{NUMBER_FORMATTER.format(chartValues[index])}</strong>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>

      <div className="dashboard-secondary-grid">
        <section className="dashboard-panel" aria-labelledby="alerts-title">
          <div className="dashboard-panel__header">
            <div>
              <p className="dashboard-panel__eyebrow">Ưu tiên vận hành</p>
              <h2 id="alerts-title">Cảnh báo gần đây</h2>
            </div>
            <button type="button" className="dashboard-text-button" onClick={() => setPage('alerts')}>
              Xem cảnh báo <i className="fa-solid fa-arrow-right" aria-hidden="true" />
            </button>
          </div>

          {pendingAlerts.length === 0 ? (
            <div className="dashboard-empty-state dashboard-empty-state--compact">
              <i className="fa-solid fa-circle-check" aria-hidden="true" />
              <div>
                <strong>Không có cảnh báo chờ xử lý</strong>
                <p>Hệ thống đang vận hành trong ngưỡng an toàn.</p>
              </div>
            </div>
          ) : (
            <div className="dashboard-alert-list">
              {pendingAlerts.map((alert) => (
                <button
                  type="button"
                  className="dashboard-alert-item"
                  key={alert.id}
                  onClick={() => setPage('alerts')}
                >
                  <span className="dashboard-alert-item__icon" aria-hidden="true">
                    <i className="fa-solid fa-triangle-exclamation" />
                  </span>
                  <span className="dashboard-alert-item__content">
                    <strong>{alert.bin}</strong>
                    <span>Ngăn {wasteLabel(alert.compartment)} đã đạt {alert.fill}%</span>
                  </span>
                  <span className="dashboard-alert-item__time">{alert.time}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="dashboard-panel" aria-labelledby="ranking-title">
          <div className="dashboard-panel__header">
            <div>
              <p className="dashboard-panel__eyebrow">Hiệu suất thiết bị</p>
              <h2 id="ranking-title">Xếp hạng {period.chartTitle.toLowerCase()}</h2>
            </div>
          </div>

          {ranking.length === 0 ? (
            <div className="dashboard-empty-state dashboard-empty-state--compact">
              <i className="fa-solid fa-ranking-star" aria-hidden="true" />
              <div>
                <strong>Chưa có dữ liệu xếp hạng</strong>
                <p>Cần ít nhất 1 lượt phân loại trong kỳ.</p>
              </div>
            </div>
          ) : (
            <ol className="dashboard-ranking-list">
              {ranking.slice(0, 4).map((row, index) => (
                <li key={`${row.name}-${index}`}>
                  <span className={`dashboard-rank dashboard-rank--${index + 1}`}>{index + 1}</span>
                  <span className="dashboard-ranking-list__name">{row.name}</span>
                  <strong>{NUMBER_FORMATTER.format(row.points)} lượt</strong>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </section>
  );
};
