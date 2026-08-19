// src/mockData.ts
//
// Mock CÓ CHỦ ĐÍCH — không phải fallback tạm thời chờ API.
// Đây là dữ liệu KHÔNG có endpoint backend tương ứng trong phạm vi hiện tại
// (xem De_xuat_thiet_ke_DB.md mục 5 — các phần cố ý chưa đưa vào core schema),
// nên giữ mock lâu dài cho tới khi có API thật:
//   - REWARDS: tích điểm thưởng — chưa có collection/API trong core schema.
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
