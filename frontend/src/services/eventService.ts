import { apiClient } from './apiClient';
import type { EventResponseDto, ClassifyHistoryRow } from '../types/api';

export async function fetchEvents(
  deviceId: string,
  eventType?: string,
  limit = 50
): Promise<EventResponseDto[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (eventType) params.set('eventType', eventType);
  return apiClient.get<EventResponseDto[]>(`/api/devices/${deviceId}/events?${params.toString()}`);
}

export async function fetchClassifyHistory(deviceId: string, limit = 20): Promise<ClassifyHistoryRow[]> {
  const events = await fetchEvents(deviceId, 'CLASSIFY', limit);
  return events
    .filter((e) => e.wasteType !== null)
    .map((e) => ({
      time: e.deviceTimestamp ? new Date(e.deviceTimestamp).toLocaleTimeString('vi-VN') : '',
      type: e.wasteType!,
      compartment: e.targetCompartment ?? '',
      accuracy: (e.aiConfidence ?? 0) * 100,
      // "Từ chối" trong spec = AI confidence dưới ngưỡng -> không mở nắp (FREQ.5).
      // Backend hiện không có field riêng đánh dấu "rejected"; suy đoán tạm qua
      // aiConfidence < alertThreshold. TODO: xác nhận lại với AI team field nào
      // (nếu có) đánh dấu chính xác việc bị từ chối, tránh suy đoán sai.
      result: (e.aiConfidence ?? 0) >= (e.alertThreshold ?? 0) ? 'success' : 'rejected',
    }));
}

/**
 * Cảnh báo đầy = event FULL_ALERT. Chỉ đọc, KHÔNG có khái niệm "đã xử lý" ở
 * backend hiện tại (xem De_xuat_thiet_ke_DB.md mục 5 — chưa có lifecycle
 * active/resolved). "Xử lý" ở AlertsPage nên tạm giữ local state phía
 * frontend, không gọi API, cho tới khi nhóm quyết định thiết kế Alert entity.
 */
export async function fetchFullAlerts(deviceId: string, limit = 50): Promise<EventResponseDto[]> {
  return fetchEvents(deviceId, 'FULL_ALERT', limit);
}

export async function resolveFullAlert(deviceId: string, eventId: string): Promise<void> {
  await apiClient.patch<void>(`/api/devices/${deviceId}/events/${eventId}/resolve`, {});
}
