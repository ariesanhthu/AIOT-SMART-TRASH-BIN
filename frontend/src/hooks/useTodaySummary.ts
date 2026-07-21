import { useEffect, useState } from 'react';
import { fetchDailyStatsSummary } from '../services/statsService';
import type { DailyStatSummaryDto } from '../types/api';

const EMPTY: DailyStatSummaryDto = {
  date: '', organicCount: 0, paperCount: 0, plasticCount: 0, recyclableCount: 0, totalCount: 0,
};

export function useTodaySummary(days = 1) {
  const [summary, setSummary] = useState<DailyStatSummaryDto>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      fetchDailyStatsSummary(days)
        .then((data) => { if (!cancelled) setSummary(data); })
        .finally(() => { if (!cancelled && showLoading) setLoading(false); });
    };
    load(true);
    const timer = window.setInterval(() => load(false), 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [days]);

  return { summary, loading };
}