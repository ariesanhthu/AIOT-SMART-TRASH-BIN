import { useEffect, useState } from 'react';
import { fetchDailyStats, toDailyChartData } from '../services/statsService';
import type { DailyChartData } from '../types/api';

const EMPTY: DailyChartData = { labels: [], organic: [], paper: [], plastic: [] };

export function useDailyStats(deviceId: string | null, days = 7) {
  const [data, setData] = useState<DailyChartData>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!deviceId) return;
    let cancelled = false;

    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      const to = new Date();
      const from = new Date();
      from.setDate(to.getDate() - (days - 1));

      fetchDailyStats(deviceId, formatDate(from), formatDate(to))
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
  }, [deviceId, days]);

  return { data, loading };
}

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
