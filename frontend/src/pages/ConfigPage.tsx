import React, { useState } from 'react';
import { THRESHOLDS } from '../data';

interface Props {
  showToast: (msg: string) => void;
}

export const ConfigPage: React.FC<Props> = ({ showToast }) => {
  const [globalConf, setGlobalConf] = useState(85);
  const [orgConf, setOrgConf] = useState(80);
  const [recConf, setRecConf] = useState(88);
  const [inorgConf, setInorgConf] = useState(82);

  const [currentBin, setCurrentBin] = useState('A1');
  const binThresholds = (THRESHOLDS as any)[currentBin] || { organic: 80, recycle: 85, inorganic: 90 };

  const [orgThresh, setOrgThresh] = useState(binThresholds.organic);
  const [recThresh, setRecThresh] = useState(binThresholds.recycle);
  const [inorgThresh, setInorgThresh] = useState(binThresholds.inorganic);

  const [mqttUrl, setMqttUrl] = useState('mqtt://hivemq.cloud:8883');
  const [topic, setTopic] = useState('smartbin/hcmus/');
  const [interval, setIntervalVal] = useState(30);

  React.useEffect(() => {
    const t = (THRESHOLDS as any)[currentBin] || { organic: 80, recycle: 85, inorganic: 90 };
    setOrgThresh(t.organic);
    setRecThresh(t.recycle);
    setInorgThresh(t.inorganic);
  }, [currentBin]);

  const handleSave = (type: string) => {
    if (type === 'ai') showToast('Đã lưu cấu hình AI!');
    if (type === 'threshold') showToast('Đã lưu ngưỡng cảnh báo!');
    if (type === 'network') showToast('Đã lưu cấu hình mạng!');
  };

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Cấu hình Hệ thống</h1>
          <p className="subtitle body-md">Quản lý ngưỡng AI và cảnh báo cho từng thùng / ngăn</p>
        </div>
      </div>

      <div className="grid-2 mb-6">
        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#f3e8ff', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-robot" style={{ color: '#9333ea' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Ngưỡng tin cậy AI</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Điểm confidence tối thiểu để chấp nhận kết quả</p>
            </div>
          </div>

          <div className="space-y-6">
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="body-md" style={{ fontWeight: 500, color: 'var(--on-surface)' }}>Ngưỡng tổng quát</label>
                <span className="badge badge-pill badge-success" style={{ fontWeight: 700 }}>{globalConf}%</span>
              </div>
              <input type="range" min="50" max="99" value={globalConf} onChange={(e) => setGlobalConf(Number(e.target.value))} />
              <div className="flex justify-between mt-1" style={{ fontSize: '11px', color: 'var(--outline)' }}><span>50%</span><span>99%</span></div>
              <p style={{ fontSize: '11px', color: 'var(--outline)', marginTop: '8px' }}>Áp dụng cho tất cả thùng nếu không cấu hình riêng</p>
            </div>
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="body-md" style={{ fontWeight: 500, color: 'var(--on-surface)' }}>Hữu cơ (Organic)</label>
                <span className="badge badge-pill badge-success" style={{ fontWeight: 700 }}>{orgConf}%</span>
              </div>
              <input type="range" min="50" max="99" value={orgConf} onChange={(e) => setOrgConf(Number(e.target.value))} />
            </div>
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="body-md" style={{ fontWeight: 500, color: 'var(--on-surface)' }}>Tái chế (Recyclable)</label>
                <span className="badge badge-pill badge-info" style={{ fontWeight: 700 }}>{recConf}%</span>
              </div>
              <input type="range" min="50" max="99" value={recConf} onChange={(e) => setRecConf(Number(e.target.value))} />
            </div>
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="body-md" style={{ fontWeight: 500, color: 'var(--on-surface)' }}>Vô cơ (Inorganic)</label>
                <span className="badge badge-pill badge-neutral" style={{ fontWeight: 700 }}>{inorgConf}%</span>
              </div>
              <input type="range" min="50" max="99" value={inorgConf} onChange={(e) => setInorgConf(Number(e.target.value))} />
            </div>
          </div>

          <button onClick={() => handleSave('ai')} className="btn btn-primary w-full mt-6" style={{ justifyContent: 'center' }}>
            <i className="fa-solid fa-floppy-disk"></i> Lưu cấu hình AI
          </button>
        </div>

        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#fef3c7', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-gauge" style={{ color: '#d97706' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Ngưỡng báo đầy</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Cấu hình % đầy riêng cho từng ngăn</p>
            </div>
          </div>

          <div className="filter-group mb-5" style={{ display: 'flex' }}>
            {['A1', 'A2', 'B1', 'B2', 'C1'].map(b => (
              <button key={b} onClick={() => setCurrentBin(b)} className={`time-btn ${currentBin === b ? 'active-time' : ''}`} style={{ flex: 1, textAlign: 'center', border: 'none' }}>
                {b}
              </button>
            ))}
          </div>

          <div className="space-y-5">
            <div style={{ padding: '16px', background: 'var(--surface-container-low)', borderRadius: 'var(--radius-lg)', border: '1px solid #E3E8E1' }}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <i className="fa-solid fa-leaf" style={{ color: '#22c55e', fontSize: '14px' }}></i>
                  <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Ngăn Hữu cơ</span>
                </div>
                <span className="badge badge-pill" style={{ fontWeight: 700, background: '#dcfce7', color: '#22c55e' }}>{orgThresh}%</span>
              </div>
              <input type="range" min="50" max="100" value={orgThresh} onChange={(e) => setOrgThresh(Number(e.target.value))} />
            </div>

            <div style={{ padding: '16px', background: 'var(--surface-container-low)', borderRadius: 'var(--radius-lg)', border: '1px solid #E3E8E1' }}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <i className="fa-solid fa-recycle" style={{ color: '#3b82f6', fontSize: '14px' }}></i>
                  <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Ngăn Nhựa</span>
                </div>
                <span className="badge badge-pill" style={{ fontWeight: 700, background: '#dbeafe', color: '#3b82f6' }}>{recThresh}%</span>
              </div>
              <input type="range" min="50" max="100" value={recThresh} onChange={(e) => setRecThresh(Number(e.target.value))} />
            </div>

            <div style={{ padding: '16px', background: 'var(--surface-container-low)', borderRadius: 'var(--radius-lg)', border: '1px solid #E3E8E1' }}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <i className="fa-solid fa-newspaper" style={{ color: '#f59e0b', fontSize: '14px' }}></i>
                  <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>Ngăn Giấy</span>
                </div>
                <span className="badge badge-pill" style={{ fontWeight: 700, background: '#fef3c7', color: '#f59e0b' }}>{inorgThresh}%</span>
              </div>
              <input type="range" min="50" max="100" value={inorgThresh} onChange={(e) => setInorgThresh(Number(e.target.value))} />
            </div>
          </div>

          <button onClick={() => handleSave('threshold')} className="btn w-full mt-6" style={{ justifyContent: 'center', background: '#d97706', color: '#fff' }}>
            <i className="fa-solid fa-floppy-disk"></i> Lưu ngưỡng cảnh báo
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
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Kết nối & Mạng</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>MQTT broker và endpoint telemetry</p>
            </div>
          </div>
          <div className="space-y-4">
            <div>
              <label className="label-caps" style={{ color: 'var(--outline)', display: 'block', marginBottom: '6px' }}>MQTT Broker URL</label>
              <input type="text" value={mqttUrl} onChange={e => setMqttUrl(e.target.value)} className="input-field" />
            </div>
            <div>
              <label className="label-caps" style={{ color: 'var(--outline)', display: 'block', marginBottom: '6px' }}>Topic prefix</label>
              <input type="text" value={topic} onChange={e => setTopic(e.target.value)} className="input-field" />
            </div>
            <div>
              <label className="label-caps" style={{ color: 'var(--outline)', display: 'block', marginBottom: '6px' }}>Telemetry interval (giây)</label>
              <input type="number" value={interval} onChange={e => setIntervalVal(Number(e.target.value))} min={5} max={300} className="input-field" />
            </div>
          </div>
          <button onClick={() => handleSave('network')} className="btn w-full mt-6" style={{ justifyContent: 'center', background: '#3b82f6', color: '#fff', border: 'none' }}>
            <i className="fa-solid fa-floppy-disk"></i> Lưu cấu hình mạng
          </button>
        </div>

        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#ccfbf1', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-brain" style={{ color: '#0d9488' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Quản lý Model AI</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Phiên bản và deployment</p>
            </div>
          </div>
          <div className="space-y-3">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'var(--primary-fixed)', borderRadius: 'var(--radius-lg)', border: '1px solid rgba(31,122,77,0.2)' }}>
              <div className="flex items-center gap-3">
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--primary-container)' }}></span>
                <div>
                  <p className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>trashnet-tflite-v1.2</p>
                  <p style={{ fontSize: '12px', color: 'var(--outline)' }}>Đang chạy · Triển khai 12/05/2026</p>
                </div>
              </div>
              <span className="badge badge-pill badge-success">Active</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'var(--surface-container-low)', borderRadius: 'var(--radius-lg)', border: '1px solid #E3E8E1' }}>
              <div className="flex items-center gap-3">
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--outline-variant)' }}></span>
                <div>
                  <p className="body-md" style={{ fontWeight: 600, color: 'var(--outline)' }}>trashnet-tflite-v1.1</p>
                  <p style={{ fontSize: '12px', color: 'var(--outline-variant)' }}>Đã dừng · Triển khai 01/04/2026</p>
                </div>
              </div>
              <span className="badge badge-pill badge-neutral">Inactive</span>
            </div>
          </div>
          <div style={{ marginTop: '16px', padding: '12px', background: '#fef3c7', border: '1px solid #fde68a', borderRadius: 'var(--radius-lg)' }}>
            <p style={{ fontSize: '12px', color: '#92400e' }}>
              <i className="fa-solid fa-circle-info mr-1"></i>
              Trước khi triển khai model mới, hệ thống sẽ chạy validation tự động trên 100 mẫu kiểm thử.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};
