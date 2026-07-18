import EspCamera from '../components/EspCam';

export const CameraPage = () => {
  return (
    <section className="page-section camera-page">
      <div className="page-header camera-page__header">
        <div>
          <h1>Stream camera</h1>
          <p className="subtitle body-md">
            Theo dõi luồng ESP32-CAM và chụp ảnh kiểm tra phân loại rác theo thời gian thực
          </p>
        </div>

        <div className="camera-page__status">
          <span className="status-dot status-online"></span>
          <span>ESP32-CAM</span>
        </div>
      </div>

      <EspCamera />
    </section>
  );
};
