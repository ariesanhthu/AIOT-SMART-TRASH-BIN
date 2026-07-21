import { apiClient } from './apiClient';
import { deviceResponseToBin, deviceResponseToThresholds } from '../mappers/deviceMapper';
import type { DeviceResponseDto, UpdateDeviceConfigRequestDto, Bin } from '../types/api';
import type { WasteTypeKey } from '../constants/wasteTypes';

export async function fetchAllBins(): Promise<Bin[]> {
  const dtos = await apiClient.get<DeviceResponseDto[]>('/api/devices');
  return dtos.map(deviceResponseToBin);
}

export async function fetchBinThresholds(deviceId: string): Promise<Partial<Record<WasteTypeKey, number>>> {
  const dto = await apiClient.get<DeviceResponseDto>(`/api/devices/${deviceId}`);
  return deviceResponseToThresholds(dto);
}

export async function updateDeviceConfig(
  deviceId: string,
  body: UpdateDeviceConfigRequestDto
): Promise<void> {
  await apiClient.patch<void>(`/api/devices/${deviceId}/config`, body);
}