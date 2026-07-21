import { apiClient } from './apiClient';
import type { DailyStatDto, DailyChartData, DailyStatSummaryDto, DeviceRankDto } from '../types/api';

export async function fetchDailyStats(deviceId: string, from: string, to: string): Promise<DailyStatDto[]> {
  const params = new URLSearchParams({ deviceId, from, to });
  return apiClient.get<DailyStatDto[]>(`/api/daily-stats?${params.toString()}`);
}

export function toDailyChartData(stats: DailyStatDto[]): DailyChartData {
  return {
    labels: stats.map((s) => s.date),
    organic: stats.map((s) => s.organicCount),
    paper: stats.map((s) => s.paperCount),
    plastic: stats.map((s) => s.plasticCount),
  };
}

export async function fetchDailyStatsSummary(days = 1): Promise<DailyStatSummaryDto> {
  return apiClient.get<DailyStatSummaryDto>(`/api/daily-stats/summary?days=${days}`);
}

export async function fetchRanking(days = 7): Promise<DeviceRankDto[]> {
  return apiClient.get<DeviceRankDto[]>(`/api/daily-stats/ranking?days=${days}`);
}