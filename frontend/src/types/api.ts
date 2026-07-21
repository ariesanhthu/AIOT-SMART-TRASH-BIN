import type { WasteTypeKey } from '../constants/wasteTypes';

export interface CompartmentDto {
  threshold: number | null;
  fillPercent: number | null;
  status: string | null;
}

export interface DeviceResponseDto {
  deviceId: string;
  name: string | null;
  location: string | null;
  lastSeenAt: string | null;
  maintenanceMode: boolean;
  firmwareVersion: string | null;
  aiModelVersion: string | null;
  className: string | null;
  compartments: Partial<Record<WasteTypeKey, CompartmentDto>>;
}

export interface EventResponseDto {
  id: string;
  eventType: string;
  wasteType: WasteTypeKey | 'REJECTED' | null;
  targetCompartment: string | null;
  aiConfidence: number | null;
  fillPercent: Partial<Record<WasteTypeKey, number>> | null;
  alertThreshold: number | null;
  deviceTimestamp: string | null;
  receivedAt: string | null;
  syncedLate: boolean;
  firmwareVersion: string | null;
  aiModelVersion: string | null;
  alertStatus: 'pending' | 'resolved' | null;
  resolvedAt: string | null;
  resolvedBy: string | null;
}

export interface DailyStatDto {
  deviceId: string;
  date: string;
  organicCount: number;
  paperCount: number;
  plasticCount: number;
  totalCount: number;
}

export interface UpdateDeviceConfigRequestDto {
  thresholds?: Partial<Record<WasteTypeKey, number>>;
  maintenanceMode?: boolean;
}

export interface Bin {
  id: string;
  name: string;
  location: string;
  className: string | null; 
  online: boolean;
  maintenanceMode: boolean;
  compartments: Partial<Record<WasteTypeKey, number>>;
  thresholds: Partial<Record<WasteTypeKey, number>>;
}

export interface BinThresholds {
  [key: string]: Partial<Record<WasteTypeKey, number>>;
}

export interface ClassifyHistoryRow {
  time: string;
  wasteType: WasteTypeKey | 'REJECTED' | null;
  compartment: string;
  result: 'success' | 'rejected';
}

export interface DailyChartData {
  labels: string[];
  organic: number[];
  paper: number[];
  plastic: number[];
}

export interface AlertRow {
  id: string;
  binId: string;
  bin: string;
  type: WasteTypeKey;
  compartment: WasteTypeKey;
  date: string;
  time: string;
  fill: number;
  status: 'pending' | 'resolved';
}

export interface DailyStatSummaryDto {
  date: string;
  organicCount: number;
  paperCount: number;
  plasticCount: number;
  recyclableCount: number;
  totalCount: number;
}

export interface DeviceRankDto {
  deviceId: string;
  totalCount: number;
}