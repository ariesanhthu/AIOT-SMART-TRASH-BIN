import { useEffect, useState } from 'react';
import { fetchDailyStats, toDailyChartData } from '../services/statsService';
import type { DailyChartData } from '../types/api';

const EMPTY: DailyChartData = { labels: [], organic: [], paper: [], plastic: [] };

export function useDailyStats(deviceId: string | null, from: string, to: string) {
  const [data, setData] = useState<DailyChartData>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!deviceId || !from || !to) return;
    let cancelled = false;

    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      fetchDailyStats(deviceId, from, to)
        .then((stats) => {
          if (!cancelled) setData(toDailyChartData(stats));
        })
        .finally(() => {
          if (!cancelled && showLoading) setLoading(false);
        });
    };

    load(true);
    const timer = window.setInterval(() => load(false), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [deviceId, from, to]);

  return { data, loading };
}