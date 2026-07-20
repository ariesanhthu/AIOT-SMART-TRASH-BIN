import type { DeviceResponseDto, Bin, BinThresholds } from '../types/api';
import type { WasteTypeKey } from '../constants/wasteTypes';
import { WASTE_TYPE_KEYS } from '../constants/wasteTypes';

export function deviceResponseToBin(dto: DeviceResponseDto): Bin {
  const compartments: Partial<Record<WasteTypeKey, number>> = {};
  const thresholds: Partial<Record<WasteTypeKey, number>> = {};

  for (const key of WASTE_TYPE_KEYS) {
    const c = dto.compartments[key];
    if (c) {
      compartments[key] = c.fillPercent ?? 0;
      if (c.threshold != null) thresholds[key] = normalizeThreshold(c.threshold);
    }
  }

  return {
    id: dto.deviceId,
    name: dto.name ?? dto.deviceId,
    location: dto.location ?? '',
    maintenanceMode: dto.maintenanceMode,
    // "online" không có field riêng ở backend hiện tại — suy ra tạm từ lastSeenAt
    // (vd: coi là online nếu lastSeenAt trong vòng 5 phút gần nhất).
    // TODO: thống nhất với nhóm ngưỡng thời gian chính thức, hoặc thêm field
    // "online" tính sẵn ở Cloud Function/backend thay vì tính ở frontend.
    online: isRecentlySeen(dto.lastSeenAt),
    compartments,
    thresholds,
  };
}

export function deviceResponseToThresholds(dto: DeviceResponseDto): Partial<Record<WasteTypeKey, number>> {
  const thresholds: Partial<Record<WasteTypeKey, number>> = {};
  for (const key of WASTE_TYPE_KEYS) {
    const c = dto.compartments[key];
    if (c && c.threshold != null) {
      thresholds[key] = normalizeThreshold(c.threshold);
    }
  }
  return thresholds;
}

export function devicesToThresholdsMap(dtos: DeviceResponseDto[]): BinThresholds {
  const map: BinThresholds = {};
  for (const dto of dtos) {
    map[dto.deviceId] = deviceResponseToThresholds(dto);
  }
  return map;
}

function isRecentlySeen(lastSeenAt: string | null, thresholdMs = 5 * 60 * 1000): boolean {
  if (!lastSeenAt) return false;
  const diff = Date.now() - new Date(lastSeenAt).getTime();
  return diff >= 0 && diff <= thresholdMs;
}

function normalizeThreshold(value: number): number {
  return value <= 1 ? Math.round(value * 100) : value;
}
