import { apiClient } from './apiClient';
import type { DailyStatDto, DailyChartData } from '../types/api';

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