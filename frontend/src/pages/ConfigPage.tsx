import React, { useEffect, useMemo, useState } from 'react';
import { AI_CONFIDENCE_DEFAULTS, MODEL_VERSION_LIST, MQTT_DEFAULTS } from '../mockData';
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
  const [globalConf, setGlobalConf] = useState(Math.round(AI_CONFIDENCE_DEFAULTS.confidenceMin * 100));
  const [orgConf, setOrgConf] = useState(80);
  const [paperConf, setPaperConf] = useState(88);
  const [plasticConf, setPlasticConf] = useState(82);
  const [currentBinId, setCurrentBinId] = useState(bins[0]?.id ?? '');
  const [thresholds, setThresholds] = useState<Record<WasteTypeKey, number>>({
    organic: 80,
    paper: 80,
    plastic: 80,
  });
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [savingThreshold, setSavingThreshold] = useState(false);
  const [mqttUrl, setMqttUrl] = useState(MQTT_DEFAULTS.brokerUrl);
  const [topic, setTopic] = useState(MQTT_DEFAULTS.topicPrefix);
  const [interval, setIntervalVal] = useState(30);

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
      showToast('Da luu nguong canh bao xuong backend!');
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Khong the luu cau hinh');
    } finally {
      setSavingThreshold(false);
    }
  };

  const handleSave = (type: string) => {
    if (type === 'ai') showToast('Cau hinh AI dang la thong tin tham khao trong prototype.');
    if (type === 'network') showToast('Cau hinh mang/MQTT dang la placeholder cho huong nang cap.');
  };

  if (bins.length === 0) {
    return (
      <section className="page-section">
        <div className="page-header">
          <div>
            <h1>Cau hinh he thong</h1>
            <p className="subtitle body-md">Chua co thiet bi nao de cau hinh.</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Cau hinh he thong</h1>
          <p className="subtitle body-md">Quan ly nguong AI va nguong day cho tung thung / ngan</p>
        </div>
      </div>

      <div className="grid-2 mb-6">
        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#f3e8ff', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-robot" style={{ color: '#9333ea' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Nguong tin cay AI</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Thong tin tham khao, chua ghi DB trong prototype</p>
            </div>
          </div>

          <div className="space-y-6">
            <RangeField label="Nguong tong quat" value={globalConf} onChange={setGlobalConf} badgeClass="badge-success" />
            <RangeField label="Huu co (Organic)" value={orgConf} onChange={setOrgConf} badgeClass="badge-success" />
            <RangeField label="Giay (Paper)" value={paperConf} onChange={setPaperConf} badgeClass="badge-neutral" />
            <RangeField label="Nhua (Plastic)" value={plasticConf} onChange={setPlasticConf} badgeClass="badge-info" />
          </div>

          <button onClick={() => handleSave('ai')} className="btn btn-primary w-full mt-6" style={{ justifyContent: 'center' }}>
            <i className="fa-solid fa-circle-info"></i> Ghi chu cau hinh AI
          </button>
        </div>

        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#fef3c7', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-gauge" style={{ color: '#d97706' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Nguong bao day</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Luu that qua PATCH /api/devices/id/config</p>
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
                      <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Ngan {wt.label}</span>
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
            Bat che do bao tri cho thiet bi nay
          </label>

          <button onClick={saveThresholds} disabled={savingThreshold} className="btn w-full mt-6" style={{ justifyContent: 'center', background: '#d97706', color: '#fff' }}>
            <i className="fa-solid fa-floppy-disk"></i> {savingThreshold ? 'Dang luu...' : 'Luu cau hinh thiet bi'}
          </button>
        </div>
      </div>

      <div className="grid-2">
        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#dbeafe', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-network-wired" style={{ color: '#3b82f6' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Ket noi & mang</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Placeholder cho huong nang cap MQTT</p>
            </div>
          </div>
          <div className="space-y-4">
            <InputField label="MQTT Broker URL" value={mqttUrl} onChange={setMqttUrl} />
            <InputField label="Topic prefix" value={topic} onChange={setTopic} />
            <div>
              <label className="label-caps" style={{ color: 'var(--outline)', display: 'block', marginBottom: '6px' }}>Telemetry interval (giay)</label>
              <input type="number" value={interval} onChange={(e) => setIntervalVal(Number(e.target.value))} min={5} max={300} className="input-field" />
            </div>
          </div>
          <button onClick={() => handleSave('network')} className="btn w-full mt-6" style={{ justifyContent: 'center', background: '#3b82f6', color: '#fff', border: 'none' }}>
            <i className="fa-solid fa-circle-info"></i> Ghi chu cau hinh mang
          </button>
        </div>

        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#ccfbf1', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-brain" style={{ color: '#0d9488' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Quan ly model AI</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Version dang chay lay tu thiet bi, danh sach duoi day la minh hoa</p>
            </div>
          </div>

          <div className="space-y-3">
            <div style={{ padding: '12px', background: 'var(--primary-fixed)', borderRadius: 'var(--radius-lg)', border: '1px solid rgba(31,122,77,0.2)' }}>
              <p className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>{currentBin?.id}: {bins.find((bin) => bin.id === currentBin?.id)?.name}</p>
              <p style={{ fontSize: '12px', color: 'var(--outline)' }}>Model dang bao cao qua API thiet bi</p>
            </div>
            {MODEL_VERSION_LIST.map((model) => (
              <div key={model.version} style={{ padding: '12px', background: 'var(--surface-container-low)', borderRadius: 'var(--radius-lg)', border: '1px solid #E3E8E1' }}>
                <p className="body-md" style={{ fontWeight: 600, color: 'var(--outline)' }}>{model.version}</p>
                <p style={{ fontSize: '12px', color: 'var(--outline-variant)' }}>Upload: {model.uploadedAt}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

function RangeField({ label, value, onChange, badgeClass }: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  badgeClass: string;
}) {
  return (
    <div>
      <div className="flex justify-between items-center mb-3">
        <label className="body-md" style={{ fontWeight: 500, color: 'var(--on-surface)' }}>{label}</label>
        <span className={`badge badge-pill ${badgeClass}`} style={{ fontWeight: 700 }}>{value}%</span>
      </div>
      <input type="range" min="50" max="99" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function InputField({ label, value, onChange }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label-caps" style={{ color: 'var(--outline)', display: 'block', marginBottom: '6px' }}>{label}</label>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} className="input-field" />
    </div>
  );
}
