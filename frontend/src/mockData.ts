// src/mockData.ts
//
// Mock CÓ CHỦ ĐÍCH — không phải fallback tạm thời chờ API.
// Đây là dữ liệu KHÔNG có endpoint backend tương ứng trong phạm vi hiện tại
// (xem De_xuat_thiet_ke_DB.md mục 5 — các phần cố ý chưa đưa vào core schema),
// nên giữ mock lâu dài cho tới khi có API thật:
//   - REWARDS: tích điểm thưởng — chưa có collection/API trong core schema.
//   - AI_CONFIDENCE_DEFAULTS: ngưỡng confidence_min/margin_min mặc định hiển thị
//     trên ConfigPage — model thật đọc threshold từ artifact (thresholds.json),
//     không phải từ Firestore, nên UI chỉ hiển thị tham khảo.
//   - MQTT_DEFAULTS: cấu hình broker mặc định cho hướng nâng cấp MQTT (mục 2.2
//     De_xuat_thiet_ke_DB.md) — chưa triển khai, chỉ hiển thị placeholder.
//   - MODEL_VERSION_LIST: danh sách model để chọn trên dashboard — FREQ.10 phần
//     upload model từ dashboard đang defer, nhóm nạp thủ công, nên danh sách này
//     chỉ mang tính minh họa UI, không đại diện model đang thực sự chạy.
//
// KHÔNG import BINS/ALERT_HISTORY/CLASSIFY_HISTORY/DAILY_DATA/THRESHOLDS ở đây
// nữa — các phần đó đã có hook thật (useBins, useFullAlerts, useClassifyHistory,
// useDailyStats) gọi services/ + mappers/. Nếu 1 page còn import mock đó thay vì
// gọi hook, đó là dấu hiệu page chưa nối API xong, cần rà lại.

export const REWARDS = [
  { name: "Lớp 3A", points: 420 },
  { name: "Lớp 4B", points: 385 },
  { name: "Lớp 2C", points: 310 },
  { name: "Lớp 5A", points: 265 },
];

// GIẢ ĐỊNH — đối chiếu lại với ConfigPage.tsx thật, đổi tên field nếu khác.
export const AI_CONFIDENCE_DEFAULTS = {
  confidenceMin: 0.6,
  marginMin: 0.15,
};

// GIẢ ĐỊNH — placeholder cho hướng nâng cấp MQTT (chưa triển khai thật).
export const MQTT_DEFAULTS = {
  brokerUrl: "mqtts://broker.hivemq.com",
  port: 8883,
  topicPrefix: "devices",
};

export const THRESHOLDS: Record<string, Record<string, number>> = {
  A1: { organic: 80, recycle: 85, inorganic: 90 },
  A2: { organic: 80, recycle: 85, inorganic: 90 },
  B1: { organic: 85, recycle: 88, inorganic: 92 },
  B2: { organic: 80, recycle: 85, inorganic: 90 },
  C1: { organic: 85, recycle: 90, inorganic: 92 },
};


// GIẢ ĐỊNH — danh sách hiển thị minh họa, không phải version đang chạy thật
// (version thật lấy từ Bin.aiModelVersion qua API).
export const MODEL_VERSION_LIST = [
  { version: "tinycnn-v1-int8", uploadedAt: "2026-06-20" },
  { version: "tinycnn-v0-int8", uploadedAt: "2026-06-05" },
];