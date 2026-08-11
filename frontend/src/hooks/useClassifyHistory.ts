import { useEffect, useState } from 'react';
import { fetchClassifyHistory } from '../services/eventService';
import type { ClassifyHistoryRow } from '../types/api';

export function useClassifyHistory(deviceId: string | null) {
  const [rows, setRows] = useState<ClassifyHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!deviceId) {
      setRows([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      fetchClassifyHistory(deviceId)
        .then((data) => {
          if (!cancelled) setRows(data);
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
  }, [deviceId]);

  return { rows, loading };
}
