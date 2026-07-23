import React, { useEffect, useMemo, useState } from 'react';
import { updateDeviceConfig } from '../services/deviceService';
import { WASTE_TYPES, WASTE_TYPE_KEYS } from '../constants/wasteTypes';
import type { Bin } from '../types/api';
import type { WasteTypeKey } from '../constants/wasteTypes';

interface Props {
  bins: Bin[];
  reloadBins: (showLoading?: boolean) => void;
  showToast: (msg: string) => void;
}

export const ConfigPage: React.FC<Props> = ({ bins, reloadBins, showToast }) => {
  const [currentBinId, setCurrentBinId] = useState(bins[0]?.id ?? '');
  const [thresholds, setThresholds] = useState<Record<WasteTypeKey, number>>({
    organic: 80,
    paper: 80,
    plastic: 80,
  });
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [savingThreshold, setSavingThreshold] = useState(false);

  const currentBin = useMemo(
    () => bins.find((bin) => bin.id === currentBinId) ?? bins[0],
    [bins, currentBinId]
  );

  useEffect(() => {
    if (!currentBinId && bins[0]) {
      setCurrentBinId(bins[0].id);
    }
  }, [bins, currentBinId]);

  useEffect(() => {
    if (!currentBin) return;
    setMaintenanceMode(currentBin.maintenanceMode);
    setThresholds({
      organic: currentBin.thresholds.organic ?? 80,
      paper: currentBin.thresholds.paper ?? 80,
      plastic: currentBin.thresholds.plastic ?? 80,
    });
  }, [currentBin]);

  const setThreshold = (key: WasteTypeKey, value: number) => {
    setThresholds((prev) => ({ ...prev, [key]: value }));
  };

  const saveThresholds = async () => {
    if (!currentBin) return;
    setSavingThreshold(true);
    try {
      await updateDeviceConfig(currentBin.id, {
        thresholds: {
          organic: thresholds.organic / 100,
          paper: thresholds.paper / 100,
          plastic: thresholds.plastic / 100,
        },
        maintenanceMode,
      });
      reloadBins(false);
      showToast('Đã lưu ngưỡng cảnh báo xuống backend!');
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Không thể lưu cấu hình');
    } finally {
      setSavingThreshold(false);
    }
  };

  if (bins.length === 0) {
    return (
      <section className="page-section">
        <div className="page-header">
          <div>
            <h1>Cấu hình hệ thống</h1>
            <p className="subtitle body-md">Chưa có thiết bị nào để cấu hình.</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Cấu hình hệ thống</h1>
          <p className="subtitle body-md">Quản lý ngưỡng báo đầy cho từng thùng/ngăn</p>
        </div>
      </div>

      <div className="config-page-center">
        <div className="config-panel">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#fef3c7', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-gauge" style={{ color: '#d97706' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Ngưỡng báo đầy</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Cập nhật ngưỡng báo đầy cho từng loại rác của thiết bị</p>
            </div>
          </div>

          <select value={currentBin?.id ?? ''} onChange={(e) => setCurrentBinId(e.target.value)} className="input-field mb-5">
            {bins.map((bin) => (
              <option key={bin.id} value={bin.id}>{bin.name} - {bin.location}</option>
            ))}
          </select>

          <div className="space-y-5">
            {WASTE_TYPE_KEYS.map((key) => {
              const wt = WASTE_TYPES[key];
              return (
                <div key={key} style={{ padding: '16px', background: 'var(--surface-container-low)', borderRadius: 'var(--radius-lg)', border: '1px solid #E3E8E1' }}>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: wt.color, display: 'inline-block' }}></span>
                      <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Ngăn {wt.label}</span>
                    </div>
                    <span className={`badge badge-pill ${wt.bgClass}`} style={{ fontWeight: 700 }}>{thresholds[key]}%</span>
                  </div>
                  <input type="range" min="50" max="100" value={thresholds[key]} onChange={(e) => setThreshold(key, Number(e.target.value))} />
                </div>
              );
            })}
          </div>

          <label className="flex items-center gap-2 mt-5 body-md" style={{ color: 'var(--on-surface)' }}>
            <input type="checkbox" checked={maintenanceMode} onChange={(e) => setMaintenanceMode(e.target.checked)} />
            Bật chế độ bảo trì cho thiết bị này
          </label>

          <button onClick={saveThresholds} disabled={savingThreshold} className="btn w-full mt-6" style={{ justifyContent: 'center', background: '#d97706', color: '#fff' }}>
            <i className="fa-solid fa-floppy-disk"></i> {savingThreshold ? 'Đang lưu...' : 'Lưu cấu hình thiết bị'}
          </button>
        </div>
      </div>
    </section>
  );
};
